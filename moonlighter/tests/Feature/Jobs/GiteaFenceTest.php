<?php

declare(strict_types=1);

namespace Tests\Feature\Jobs;

use App\Enums\JobStatus;
use App\Models\NightCrewJob;
use App\Models\Worker;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Client\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Http;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

class GiteaFenceTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        Carbon::setTestNow(Carbon::parse('2026-09-21 13:00:00', 'UTC')); // Mon 09:00 EDT
    }

    protected function tearDown(): void
    {
        Carbon::setTestNow();
        parent::tearDown();
    }

    private const REPO = 'owner/project';

    /**
     * Point the fence at a fake Gitea instance with a known bot identity.
     */
    private function configureFence(): void
    {
        config([
            'nightcrew.gitea.base_url' => 'http://gitea.test/api/v1',
            'nightcrew.gitea.token' => 'test-token',
            'nightcrew.gitea.bot' => 'night-crew-bot',
            'nightcrew.gitea.labels.in_progress' => 'status: in-progress',
            'nightcrew.gitea.labels.complete' => 'status: complete',
        ]);
    }

    /**
     * Authenticate as a worker serving the test repo.
     *
     * @param  string  $workerId
     */
    private function actAsWorker(string $workerId): Worker
    {
        $worker = Worker::factory()->serving([self::REPO])->create(['worker_id' => $workerId]);
        Sanctum::actingAs($worker);

        return $worker;
    }

    /**
     * Claiming an issue assigns the bot, labels it in-progress, and comments.
     */
    public function test_claiming_an_issue_fences_the_gitea_ticket(): void
    {
        $this->configureFence();
        Http::fake(['gitea.test/*' => Http::response(['assignees' => [], 'labels' => []], 200)]);
        $this->actAsWorker('nas-01');
        NightCrewJob::factory()->forRepo(self::REPO)->create(['reference' => '#42']);

        $this->postJson('/api/claim-next')->assertOk();

        Http::assertSent(fn (Request $request): bool => str_contains($request->url(), '/issues/42/labels') && $request->method() === 'POST');
        Http::assertSent(fn (Request $request): bool => str_contains($request->url(), '/issues/42/comments') && $request->method() === 'POST');
        Http::assertSent(fn (Request $request): bool => str_ends_with($request->url(), '/issues/42') && $request->method() === 'PATCH');
    }

    /**
     * An issue a human already holds is handed back, not claimed.
     */
    public function test_human_held_issue_is_released_not_claimed(): void
    {
        $this->configureFence();
        Http::fake(['gitea.test/*' => Http::response(['assignees' => [['login' => 'operator']], 'labels' => []], 200)]);
        $this->actAsWorker('nas-01');
        $job = NightCrewJob::factory()->forRepo(self::REPO)->create(['reference' => '#42']);

        $this->postJson('/api/claim-next')->assertNoContent();

        $job->refresh();
        $this->assertSame(JobStatus::Queued, $job->status);
        $this->assertNull($job->worker_id);
        // The fence read the issue but never wrote a claim onto it.
        Http::assertNotSent(fn (Request $request): bool => str_contains($request->url(), '/labels'));
    }

    /**
     * A Gitea failure does not roll back or block the claim.
     */
    public function test_gitea_failure_does_not_block_the_claim(): void
    {
        $this->configureFence();
        Http::fake(['gitea.test/*' => Http::response('boom', 500)]);
        $this->actAsWorker('nas-01');
        $job = NightCrewJob::factory()->forRepo(self::REPO)->create(['reference' => '#42']);

        $this->postJson('/api/claim-next')->assertOk();

        $this->assertSame(JobStatus::Claimed, $job->refresh()->status);
        $this->assertSame('nas-01', $job->worker_id);
    }

    /**
     * Finishing an issue marks it complete, comments, and closes it.
     */
    public function test_finishing_an_issue_closes_the_gitea_ticket(): void
    {
        $this->configureFence();
        Http::fake(['gitea.test/*' => Http::response([], 200)]);
        $this->actAsWorker('nas-01');
        $job = NightCrewJob::factory()->forRepo(self::REPO)->runningBy('nas-01')->create(['reference' => '#42']);

        $this->patchJson("/api/jobs/{$job->id}/status", ['status' => 'done'])->assertOk();

        Http::assertSent(fn (Request $request): bool => str_contains($request->url(), '/issues/42/labels'));
        Http::assertSent(fn (Request $request): bool => str_ends_with($request->url(), '/issues/42') && $request->method() === 'PATCH');
    }

    /**
     * Maintenance jobs have no tracker ticket, so the fence never fires.
     */
    public function test_maintenance_jobs_are_never_fenced(): void
    {
        $this->configureFence();
        Http::fake();
        $this->actAsWorker('nas-01');
        NightCrewJob::factory()->forRepo(self::REPO)->maintenanceDue()->create();

        $this->postJson('/api/claim-next')->assertOk();

        Http::assertNothingSent();
    }

    /**
     * With no Gitea configured the fence is inert and makes no calls.
     */
    public function test_fence_is_inert_when_unconfigured(): void
    {
        config(['nightcrew.gitea.base_url' => '', 'nightcrew.gitea.token' => '']);
        Http::fake();
        $this->actAsWorker('nas-01');
        NightCrewJob::factory()->forRepo(self::REPO)->create(['reference' => '#42']);

        $this->postJson('/api/claim-next')->assertOk();

        Http::assertNothingSent();
    }
}
