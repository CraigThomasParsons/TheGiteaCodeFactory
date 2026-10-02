<?php

declare(strict_types=1);

namespace Tests\Feature\Schedule;

use App\Enums\JobStatus;
use App\Models\NightCrewJob;
use App\Models\NightCrewScheduleWindow;
use App\Models\Worker;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

class ClaimBlockedOutsideScheduleTest extends TestCase
{
    use RefreshDatabase;

    private const REPO = 'owner/project';

    protected function tearDown(): void
    {
        Carbon::setTestNow();
        parent::tearDown();
    }

    /**
     * Outside the active window, claim-next returns 204 and leaves the job queued.
     */
    public function test_claim_is_blocked_outside_schedule_window(): void
    {
        // Seed already has Mon–Fri 06–12; freeze to Monday 15:00 ET (outside).
        Carbon::setTestNow(Carbon::parse('2026-09-21 19:00:00', 'UTC')); // Mon 15:00 EDT

        $worker = Worker::factory()->serving([self::REPO])->create(['worker_id' => 'nas-01']);
        Sanctum::actingAs($worker);

        $job = NightCrewJob::factory()->forRepo(self::REPO)->create();

        $this->postJson('/api/claim-next')->assertNoContent();

        $this->assertSame(JobStatus::Queued, $job->refresh()->status);
        $this->assertNull($job->worker_id);
    }

    /**
     * Inside the seeded Mon–Fri 06–12 window, claim proceeds.
     */
    public function test_claim_succeeds_inside_schedule_window(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-09-21 13:00:00', 'UTC')); // Mon 09:00 EDT

        $worker = Worker::factory()->serving([self::REPO])->create(['worker_id' => 'nas-01']);
        Sanctum::actingAs($worker);

        $job = NightCrewJob::factory()->forRepo(self::REPO)->create();

        $this->postJson('/api/claim-next')
            ->assertOk()
            ->assertJsonPath('data.id', $job->id);

        $this->assertSame(JobStatus::Claimed, $job->refresh()->status);
    }

    /**
     * With all weekly windows disabled, claim is fail-closed.
     */
    public function test_claim_fail_closed_when_no_enabled_weekly(): void
    {
        NightCrewScheduleWindow::query()->update(['enabled' => false]);
        Carbon::setTestNow(Carbon::parse('2026-09-21 13:00:00', 'UTC'));

        $worker = Worker::factory()->serving([self::REPO])->create(['worker_id' => 'nas-01']);
        Sanctum::actingAs($worker);
        NightCrewJob::factory()->forRepo(self::REPO)->create();

        $this->postJson('/api/claim-next')->assertNoContent();
    }
}
