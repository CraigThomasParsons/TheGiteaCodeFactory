<?php

declare(strict_types=1);

namespace Tests\Feature\Jobs;

use App\Enums\JobStatus;
use App\Models\NightCrewJob;
use App\Models\Worker;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

class UpdateJobStatusTest extends TestCase
{
    use RefreshDatabase;

    private const REPO = 'owner/project';

    /**
     * Authenticate as a worker with the given identity.
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
     * Reporting status requires authentication.
     */
    public function test_unauthenticated_request_is_rejected(): void
    {
        $job = NightCrewJob::factory()->forRepo(self::REPO)->claimedBy('nas-01')->create();

        $this->patchJson("/api/jobs/{$job->id}/status", ['status' => 'running'])->assertUnauthorized();
    }

    /**
     * The claiming worker can move a claimed job to running.
     */
    public function test_claiming_worker_can_start_running(): void
    {
        $this->actAsWorker('nas-01');
        $job = NightCrewJob::factory()->forRepo(self::REPO)->claimedBy('nas-01')->create();

        $this->patchJson("/api/jobs/{$job->id}/status", ['status' => 'running'])
            ->assertOk()
            ->assertJsonPath('data.status', 'running');

        $this->assertSame(JobStatus::Running, $job->refresh()->status);
    }

    /**
     * A running issue job is terminal once done.
     */
    public function test_running_issue_job_terminates_on_done(): void
    {
        $this->actAsWorker('nas-01');
        $job = NightCrewJob::factory()->forRepo(self::REPO)->runningBy('nas-01')->create();

        $this->patchJson("/api/jobs/{$job->id}/status", ['status' => 'done'])
            ->assertOk()
            ->assertJsonPath('data.status', 'done');

        $this->assertSame(JobStatus::Done, $job->refresh()->status);
    }

    /**
     * A running job can be reported failed.
     */
    public function test_running_job_can_fail(): void
    {
        $this->actAsWorker('nas-01');
        $job = NightCrewJob::factory()->forRepo(self::REPO)->runningBy('nas-01')->create();

        $this->patchJson("/api/jobs/{$job->id}/status", ['status' => 'failed'])
            ->assertOk()
            ->assertJsonPath('data.status', 'failed');
    }

    /**
     * A done maintenance job recurs: it returns to the queue, due one cadence on,
     * with its claim cleared.
     */
    public function test_maintenance_job_recurs_on_done(): void
    {
        $this->freezeTime();
        $this->actAsWorker('nas-01');
        $job = NightCrewJob::factory()->forRepo(self::REPO)->maintenanceDue()->runningBy('nas-01')->create(['cadence_minutes' => 60]);

        $this->patchJson("/api/jobs/{$job->id}/status", ['status' => 'done'])
            ->assertOk()
            ->assertJsonPath('data.status', 'queued');

        $job->refresh();
        $this->assertSame(JobStatus::Queued, $job->status);
        $this->assertNull($job->worker_id);
        $this->assertNull($job->claimed_by);
        // Compare at second precision: the datetime column drops the
        // microseconds that frozen now() still carries.
        $this->assertSame(now()->toDateTimeString(), $job->last_run_at->toDateTimeString());
        $this->assertSame(now()->addMinutes(60)->toDateTimeString(), $job->next_due_at->toDateTimeString());
    }

    /**
     * Skipping running (claimed straight to done) is rejected.
     */
    public function test_illegal_transition_is_rejected(): void
    {
        $this->actAsWorker('nas-01');
        $job = NightCrewJob::factory()->forRepo(self::REPO)->claimedBy('nas-01')->create();

        $this->patchJson("/api/jobs/{$job->id}/status", ['status' => 'done'])
            ->assertUnprocessable()
            ->assertJsonValidationErrors('status');

        $this->assertSame(JobStatus::Claimed, $job->refresh()->status);
    }

    /**
     * An unknown status value is rejected by validation.
     */
    public function test_invalid_status_value_is_rejected(): void
    {
        $this->actAsWorker('nas-01');
        $job = NightCrewJob::factory()->forRepo(self::REPO)->claimedBy('nas-01')->create();

        $this->patchJson("/api/jobs/{$job->id}/status", ['status' => 'banana'])
            ->assertUnprocessable()
            ->assertJsonValidationErrors('status');
    }

    /**
     * A worker that did not claim a non-contested job cannot transition it.
     */
    public function test_non_owning_worker_cannot_transition_non_contested_job(): void
    {
        $job = NightCrewJob::factory()->forRepo(self::REPO)->claimedBy('nas-01')->create();
        $this->actAsWorker('nas-02');

        $this->patchJson("/api/jobs/{$job->id}/status", ['status' => 'running'])->assertForbidden();

        $this->assertSame(JobStatus::Claimed, $job->refresh()->status);
    }

    /**
     * Any racing worker may transition a contested job.
     */
    public function test_a_racer_can_transition_a_contested_job(): void
    {
        $job = NightCrewJob::factory()->forRepo(self::REPO)->contested()->create([
            'status' => JobStatus::Claimed,
            'worker_id' => 'nas-01',
            'claimed_by' => ['nas-01', 'nas-02'],
            'claimed_at' => now(),
        ]);
        $this->actAsWorker('nas-02');

        $this->patchJson("/api/jobs/{$job->id}/status", ['status' => 'running'])
            ->assertOk()
            ->assertJsonPath('data.status', 'running');
    }

    /**
     * A worker not among a contested job's racers is still refused.
     */
    public function test_non_racer_cannot_transition_a_contested_job(): void
    {
        $job = NightCrewJob::factory()->forRepo(self::REPO)->contested()->create([
            'status' => JobStatus::Claimed,
            'worker_id' => 'nas-01',
            'claimed_by' => ['nas-01'],
            'claimed_at' => now(),
        ]);
        $this->actAsWorker('nas-09');

        $this->patchJson("/api/jobs/{$job->id}/status", ['status' => 'running'])->assertForbidden();
    }
}
