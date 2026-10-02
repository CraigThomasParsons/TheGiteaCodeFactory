<?php

declare(strict_types=1);

namespace Tests\Feature\Jobs;

use App\Enums\JobStatus;
use App\Models\NightCrewJob;
use App\Models\User;
use App\Models\Worker;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

class ClaimNextJobTest extends TestCase
{
    use RefreshDatabase;

    private const REPO = 'owner/project';

    protected function setUp(): void
    {
        parent::setUp();

        // Seeded schedule is Mon–Fri 06:00–12:00 America/Toronto; freeze inside it
        // so claim assertions are not time-of-day flaky.
        Carbon::setTestNow(Carbon::parse('2026-09-21 13:00:00', 'UTC')); // Mon 09:00 EDT
    }

    protected function tearDown(): void
    {
        Carbon::setTestNow();
        parent::tearDown();
    }

    /**
     * Create a worker serving the given repos and authenticate as it.
     *
     * @param  array<int, string>  $repos
     * @param  string  $workerId
     */
    private function actAsWorkerServing(string $workerId, array $repos): Worker
    {
        $worker = Worker::factory()->serving($repos)->create(['worker_id' => $workerId]);
        Sanctum::actingAs($worker);

        return $worker;
    }

    /**
     * Claiming requires authentication.
     */
    public function test_unauthenticated_claim_is_rejected(): void
    {
        $this->postJson('/api/claim-next')->assertUnauthorized();
    }

    /**
     * A non-worker token cannot claim.
     */
    public function test_non_worker_token_is_forbidden(): void
    {
        Sanctum::actingAs(User::factory()->create());

        $this->postJson('/api/claim-next')->assertForbidden();
    }

    /**
     * With no actionable work the endpoint answers 204.
     */
    public function test_returns_no_content_when_nothing_actionable(): void
    {
        $this->actAsWorkerServing('nas-01', [self::REPO]);

        $this->postJson('/api/claim-next')->assertNoContent();
    }

    /**
     * A queued issue job for a served repo is claimed and stamped.
     */
    public function test_claims_a_queued_issue_job_for_a_served_repo(): void
    {
        $worker = $this->actAsWorkerServing('nas-01', [self::REPO]);
        $job = NightCrewJob::factory()->forRepo(self::REPO)->create();

        $response = $this->postJson('/api/claim-next');

        $response->assertOk();
        $response->assertJsonPath('data.id', $job->id);
        $response->assertJsonPath('data.status', 'claimed');

        $job->refresh();
        $this->assertSame(JobStatus::Claimed, $job->status);
        $this->assertSame($worker->worker_id, $job->worker_id);
        $this->assertSame([$worker->worker_id], $job->claimed_by);
        $this->assertNotNull($job->claimed_at);
    }

    /**
     * Jobs for repositories the worker does not serve are never handed out.
     */
    public function test_ignores_jobs_for_unserved_repos(): void
    {
        $this->actAsWorkerServing('nas-01', [self::REPO]);
        $job = NightCrewJob::factory()->forRepo('owner/SomethingElse')->create();

        $this->postJson('/api/claim-next')->assertNoContent();

        $this->assertSame(JobStatus::Queued, $job->refresh()->status);
    }

    /**
     * A maintenance job that is not yet due is not claimed.
     */
    public function test_skips_maintenance_not_yet_due(): void
    {
        $this->actAsWorkerServing('nas-01', [self::REPO]);
        NightCrewJob::factory()->forRepo(self::REPO)->maintenanceNotDue()->create();

        $this->postJson('/api/claim-next')->assertNoContent();
    }

    /**
     * A maintenance job that has come due is claimed.
     */
    public function test_claims_due_maintenance(): void
    {
        $this->actAsWorkerServing('nas-01', [self::REPO]);
        $job = NightCrewJob::factory()->forRepo(self::REPO)->maintenanceDue()->create();

        $this->postJson('/api/claim-next')->assertJsonPath('data.id', $job->id);
    }

    /**
     * The highest-priority actionable job is claimed first.
     */
    public function test_claims_highest_priority_first(): void
    {
        $this->actAsWorkerServing('nas-01', [self::REPO]);
        NightCrewJob::factory()->forRepo(self::REPO)->create(['priority' => 1]);
        $urgent = NightCrewJob::factory()->forRepo(self::REPO)->create(['priority' => 9]);

        $this->postJson('/api/claim-next')->assertJsonPath('data.id', $urgent->id);
    }

    /**
     * A non-contested job is never handed to a second worker.
     */
    public function test_does_not_double_claim_a_non_contested_job(): void
    {
        $job = NightCrewJob::factory()->forRepo(self::REPO)->create();

        $this->actAsWorkerServing('nas-01', [self::REPO]);
        $this->postJson('/api/claim-next')->assertJsonPath('data.id', $job->id);

        $this->actAsWorkerServing('nas-02', [self::REPO]);
        $this->postJson('/api/claim-next')->assertNoContent();

        $this->assertSame('nas-01', $job->refresh()->worker_id);
    }

    /**
     * Across several jobs and workers, every job is claimed by exactly one worker.
     */
    public function test_each_job_is_claimed_by_exactly_one_worker(): void
    {
        NightCrewJob::factory()->count(3)->forRepo(self::REPO)->create();

        $claimedIds = [];
        foreach (['nas-01', 'nas-02'] as $workerId) {
            $this->actAsWorkerServing($workerId, [self::REPO]);
            // Each worker claims until the board is empty for it.
            while (true) {
                $response = $this->postJson('/api/claim-next');
                if ($response->status() === 204) {
                    break;
                }
                $claimedIds[] = $response->json('data.id');
            }
        }

        $this->assertCount(3, $claimedIds);
        $this->assertCount(3, array_unique($claimedIds));
        $this->assertSame(0, NightCrewJob::query()->where('status', JobStatus::Queued)->count());
    }

    /**
     * A contested issue job can be raced by several distinct workers.
     */
    public function test_contested_issue_can_be_claimed_by_multiple_workers(): void
    {
        $job = NightCrewJob::factory()->forRepo(self::REPO)->contested()->create();

        $this->actAsWorkerServing('nas-01', [self::REPO]);
        $this->postJson('/api/claim-next')->assertJsonPath('data.id', $job->id);

        $this->actAsWorkerServing('nas-02', [self::REPO]);
        $this->postJson('/api/claim-next')->assertJsonPath('data.id', $job->id);

        $this->assertSame(['nas-01', 'nas-02'], $job->refresh()->claimed_by);
    }

    /**
     * The same worker cannot claim a contested job twice.
     */
    public function test_same_worker_cannot_claim_a_contested_job_twice(): void
    {
        $job = NightCrewJob::factory()->forRepo(self::REPO)->contested()->create();
        $this->actAsWorkerServing('nas-01', [self::REPO]);

        $this->postJson('/api/claim-next')->assertJsonPath('data.id', $job->id);
        $this->postJson('/api/claim-next')->assertNoContent();

        $this->assertSame(['nas-01'], $job->refresh()->claimed_by);
    }
}
