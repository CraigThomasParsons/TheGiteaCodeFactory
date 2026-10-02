<?php

declare(strict_types=1);

namespace Tests\Feature\Jobs;

use App\Events\JobClaimed;
use App\Events\JobCreated;
use App\Events\JobStatusChanged;
use App\Models\NightCrewJob;
use App\Models\Worker;
use Illuminate\Broadcasting\BroadcastEvent;
use Illuminate\Broadcasting\Channel;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\Queue;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

class JobBroadcastTest extends TestCase
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
     * Creating a job broadcasts job.created on the night-crew channel.
     */
    public function test_creating_a_job_broadcasts_job_created(): void
    {
        Event::fake([JobCreated::class]);
        $this->actAsWorker('nas-01');

        $this->postJson('/api/repos/owner/project/jobs', ['kind' => 'issue', 'reference' => '#1'])
            ->assertCreated();

        Event::assertDispatched(JobCreated::class, function (JobCreated $event): bool {
            return $event->broadcastAs() === 'job.created'
                && $event->broadcastOn() instanceof Channel
                && $event->broadcastOn()->name === 'night-crew'
                && $event->broadcastWith()['job']['reference'] === '#1';
        });
    }

    /**
     * Claiming a job broadcasts job.claimed.
     */
    public function test_claiming_broadcasts_job_claimed(): void
    {
        Event::fake([JobClaimed::class]);
        $this->actAsWorker('nas-01');
        NightCrewJob::factory()->forRepo(self::REPO)->create();

        $this->postJson('/api/claim-next')->assertOk();

        Event::assertDispatched(JobClaimed::class, function (JobClaimed $event): bool {
            return $event->broadcastAs() === 'job.claimed'
                && $event->job->worker_id === 'nas-01';
        });
    }

    /**
     * Claiming when nothing is actionable broadcasts nothing.
     */
    public function test_empty_claim_broadcasts_nothing(): void
    {
        Event::fake([JobClaimed::class]);
        $this->actAsWorker('nas-01');

        $this->postJson('/api/claim-next')->assertNoContent();

        Event::assertNotDispatched(JobClaimed::class);
    }

    /**
     * A status change broadcasts job.status-changed.
     */
    public function test_status_change_broadcasts_job_status_changed(): void
    {
        Event::fake([JobStatusChanged::class]);
        $this->actAsWorker('nas-01');
        $job = NightCrewJob::factory()->forRepo(self::REPO)->claimedBy('nas-01')->create();

        $this->patchJson("/api/jobs/{$job->id}/status", ['status' => 'running'])->assertOk();

        Event::assertDispatched(JobStatusChanged::class, function (JobStatusChanged $event) use ($job): bool {
            return $event->broadcastAs() === 'job.status-changed'
                && $event->job->id === $job->id
                && $event->broadcastWith()['job']['status'] === 'running';
        });
    }

    /**
     * Broadcasts are queued, not sent inline — so a write succeeds and never
     * depends on Reverb being reachable at request time.
     */
    public function test_broadcasts_are_queued_so_writes_survive_a_reverb_outage(): void
    {
        Queue::fake();
        $this->actAsWorker('nas-01');
        NightCrewJob::factory()->forRepo(self::REPO)->create();

        $this->postJson('/api/claim-next')->assertOk();

        // The broadcast is deferred to the queue (ShouldBroadcast), not delivered
        // synchronously during the request (which ShouldBroadcastNow would do).
        Queue::assertPushed(BroadcastEvent::class);
    }
}
