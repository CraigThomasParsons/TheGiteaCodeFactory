<?php

declare(strict_types=1);

namespace Tests\Feature\Jobs;

use App\Enums\JobKind;
use App\Enums\JobStatus;
use App\Models\NightCrewJob;
use App\Models\Worker;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

class PullRequestJobTest extends TestCase
{
    use RefreshDatabase;

    private const REPO = 'owner/project';

    /**
     * Freeze inside the seeded Mon–Fri 06:00–12:00 America/Toronto window so
     * PR claim assertions do not depend on the wall clock (claiming is
     * fail-closed outside the schedule and would return 204).
     */
    protected function setUp(): void
    {
        parent::setUp();

        Carbon::setTestNow(Carbon::parse('2026-09-21 13:00:00', 'UTC')); // Mon 09:00 EDT
    }

    /**
     * Release the frozen clock so it never leaks into other test classes.
     */
    protected function tearDown(): void
    {
        Carbon::setTestNow();
        parent::tearDown();
    }

    /** Authenticate a worker authorized for the test repository. */
    private function actAsWorker(string $workerId = 'night-reviewer'): Worker
    {
        $worker = Worker::factory()->serving([self::REPO])->create(['worker_id' => $workerId]);
        Sanctum::actingAs($worker);

        return $worker;
    }

    /** Return a valid immutable review-stage payload. */
    private function payload(string $stage = 'review', int $attempt = 0): array
    {
        return [
            'kind' => 'pull_request',
            'reference' => '26',
            'payload' => [
                'head' => str_repeat('a', 40),
                'base' => str_repeat('b', 40),
                'stage' => $stage,
                'attempt' => $attempt,
            ],
        ];
    }

    public function test_pr_intake_is_idempotent_for_revision_stage_and_attempt(): void
    {
        $this->actAsWorker();

        $first = $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload());
        $second = $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload());

        $first->assertCreated();
        $second->assertCreated()->assertJsonPath('data.id', $first->json('data.id'));
        $this->assertSame(1, NightCrewJob::query()->where('kind', JobKind::PullRequest)->count());
    }

    public function test_pr_intake_requires_authority_and_pinned_evidence(): void
    {
        Worker::factory()->serving(['owner/Other'])->create(['worker_id' => 'other']);
        Sanctum::actingAs(Worker::query()->firstOrFail());
        $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload())->assertForbidden();

        $this->actAsWorker();
        $invalid = $this->payload();
        $invalid['payload']['head'] = 'moving-branch';
        $this->postJson('/api/repos/'.self::REPO.'/jobs', $invalid)
            ->assertUnprocessable()->assertJsonValidationErrors('payload.head');
    }

    public function test_ordinary_claim_does_not_take_pr_work(): void
    {
        $this->actAsWorker();
        $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload());

        $this->postJson('/api/claim-next')->assertNoContent();
        $this->postJson('/api/claim-next?stage=resolve')->assertNoContent();
        $this->postJson('/api/claim-next?stage=review')
            ->assertOk()->assertJsonPath('data.payload.stage', 'review');
    }

    public function test_only_one_pr_job_can_be_claimed_globally(): void
    {
        $this->actAsWorker();
        $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload());
        $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload('review', 1));

        $first = $this->postJson('/api/claim-next?stage=review')->assertOk();
        $this->assertNotEmpty($first->json('data.claim_token'));

        $this->actAsWorker('second-reviewer');
        $this->postJson('/api/claim-next?stage=review')->assertNoContent();
    }

    public function test_claim_token_fences_receipts_and_safe_requeue(): void
    {
        $this->actAsWorker();
        $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload());
        $claim = $this->postJson('/api/claim-next?stage=review')->assertOk();
        $jobId = $claim->json('data.id');
        $claimToken = $claim->json('data.claim_token');

        $this->patchJson("/api/jobs/{$jobId}/status", [
            'status' => 'running',
            'claim_token' => '00000000-0000-4000-8000-000000000000',
        ])->assertForbidden();

        $receipt = ['checkpoint' => 'standards-complete', 'provider' => 'claude'];
        $this->patchJson("/api/jobs/{$jobId}/status", [
            'status' => 'running',
            'claim_token' => $claimToken,
        ])->assertOk();
        $this->patchJson("/api/jobs/{$jobId}/status", [
            'status' => 'queued',
            'claim_token' => $claimToken,
            'receipt' => $receipt,
        ])->assertOk()->assertJsonPath('data.receipt', $receipt);

        $job = NightCrewJob::query()->findOrFail($jobId);
        $this->assertSame(JobStatus::Queued, $job->status);
        $this->assertNull($job->worker_id);
        $this->assertNull($job->claim_token);
    }

    public function test_pr_history_hides_another_workers_claim_token(): void
    {
        $this->actAsWorker('first');
        $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload());
        $this->postJson('/api/claim-next?stage=review')->assertOk();

        $this->actAsWorker('second');
        $response = $this->getJson('/api/pr-jobs')->assertOk();
        $this->assertArrayNotHasKey('claim_token', $response->json('data.0'));
    }

    public function test_old_pr_claim_is_not_stolen_without_liveness_evidence(): void
    {
        $this->actAsWorker();
        $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload());
        $job = NightCrewJob::query()->firstOrFail();
        $job->forceFill([
            'status' => JobStatus::Running,
            'worker_id' => 'dead-worker',
            'claimed_by' => ['dead-worker'],
            'claimed_at' => now()->subHours(9),
            'claim_token' => '00000000-0000-4000-8000-000000000000',
        ])->save();

        $this->postJson('/api/claim-next?stage=review')->assertNoContent();
        $this->assertSame('dead-worker', $job->refresh()->worker_id);
    }

    public function test_rediscovery_requeues_failed_stage_without_duplicate(): void
    {
        $this->actAsWorker();
        $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload());
        $job = NightCrewJob::query()->firstOrFail();
        $job->forceFill(['status' => JobStatus::Failed, 'receipt' => ['error' => 'provider failed']])->save();

        $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload())
            ->assertCreated()->assertJsonPath('data.id', $job->id)
            ->assertJsonPath('data.status', 'queued')
            ->assertJsonPath('data.receipt.error', 'provider failed');
        $this->assertSame(1, NightCrewJob::query()->count());
    }

    public function test_same_worker_can_explicitly_recover_its_stale_claim(): void
    {
        $this->actAsWorker();
        $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload());
        $job = NightCrewJob::query()->firstOrFail();
        $job->forceFill([
            'status' => JobStatus::Running,
            'worker_id' => 'night-reviewer',
            'claimed_by' => ['night-reviewer'],
            'claimed_at' => now()->subHour(),
            'claim_token' => '00000000-0000-4000-8000-000000000000',
        ])->save();

        $response = $this->postJson('/api/claim-next?stage=review&recover_stale=1')->assertOk();
        $response->assertJsonPath('data.id', $job->id);
        $this->assertNotSame('00000000-0000-4000-8000-000000000000', $response->json('data.claim_token'));
    }

    public function test_pr_writer_waits_for_active_delivery_in_same_repository(): void
    {
        $this->actAsWorker();
        NightCrewJob::factory()->forRepo(self::REPO)->runningBy('delivery-worker')->create();
        $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload());

        $this->postJson('/api/claim-next?stage=review')->assertNoContent();
    }

    public function test_repeat_intake_cannot_disclose_another_workers_claim_token(): void
    {
        $this->actAsWorker('first');
        $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload());
        $this->postJson('/api/claim-next?stage=review')->assertOk();
        $this->actAsWorker('second');
        $response = $this->postJson('/api/repos/'.self::REPO.'/jobs', $this->payload())->assertCreated();
        $this->assertArrayNotHasKey('claim_token', $response->json('data'));
    }
}
