<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Enums\JobKind;
use App\Enums\JobStatus;
use App\Models\NightCrewJob;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class NightCrewJobScopesTest extends TestCase
{
    use RefreshDatabase;

    /**
     * A queued, due issue job is actionable.
     */
    public function test_actionable_includes_a_queued_due_issue_job(): void
    {
        $job = NightCrewJob::factory()->create();

        $actionableIds = NightCrewJob::query()->actionable()->pluck('id');

        $this->assertTrue($actionableIds->contains($job->id));
    }

    /**
     * A claimed job is not actionable, even if otherwise due.
     */
    public function test_actionable_excludes_a_claimed_job(): void
    {
        $job = NightCrewJob::factory()->claimed()->create();

        $actionableIds = NightCrewJob::query()->actionable()->pluck('id');

        $this->assertFalse($actionableIds->contains($job->id));
    }

    /**
     * A maintenance job whose recurrence has not arrived is not actionable.
     */
    public function test_actionable_excludes_maintenance_not_yet_due(): void
    {
        $job = NightCrewJob::factory()->maintenanceNotDue()->create();

        $actionableIds = NightCrewJob::query()->actionable()->pluck('id');

        $this->assertFalse($actionableIds->contains($job->id));
    }

    /**
     * A maintenance job that has come due is actionable.
     */
    public function test_actionable_includes_due_maintenance(): void
    {
        $job = NightCrewJob::factory()->maintenanceDue()->create();

        $actionableIds = NightCrewJob::query()->actionable()->pluck('id');

        $this->assertTrue($actionableIds->contains($job->id));
    }

    /**
     * dueMaintenance returns due maintenance jobs but never issue jobs nor
     * maintenance jobs that are not yet due.
     */
    public function test_due_maintenance_scope_selects_only_due_maintenance(): void
    {
        $due = NightCrewJob::factory()->maintenanceDue()->create();
        $notDue = NightCrewJob::factory()->maintenanceNotDue()->create();
        $issue = NightCrewJob::factory()->create();

        $dueIds = NightCrewJob::query()->dueMaintenance()->pluck('id');

        $this->assertTrue($dueIds->contains($due->id));
        $this->assertFalse($dueIds->contains($notDue->id));
        $this->assertFalse($dueIds->contains($issue->id));
    }

    /**
     * The due boundary is inclusive: next_due_at exactly equal to now is due.
     */
    public function test_due_boundary_is_inclusive(): void
    {
        $this->freezeTime();
        $job = NightCrewJob::factory()->create(['next_due_at' => now()]);

        $actionableIds = NightCrewJob::query()->actionable()->pluck('id');

        $this->assertTrue($actionableIds->contains($job->id));
    }

    /**
     * kind and status round-trip through their enum casts, proving the schema
     * and casts line up.
     */
    public function test_kind_and_status_cast_to_enums(): void
    {
        $job = NightCrewJob::factory()->maintenanceDue()->claimed()->create();
        $fresh = $job->fresh();

        $this->assertInstanceOf(JobKind::class, $fresh->kind);
        $this->assertSame(JobKind::Maintenance, $fresh->kind);
        $this->assertInstanceOf(JobStatus::class, $fresh->status);
        $this->assertSame(JobStatus::Claimed, $fresh->status);
        $this->assertIsInt($fresh->cadence_minutes);
    }
}
