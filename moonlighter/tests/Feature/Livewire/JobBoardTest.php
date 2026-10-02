<?php

declare(strict_types=1);

namespace Tests\Feature\Livewire;

use App\Enums\JobKind;
use App\Enums\JobStatus;
use App\Livewire\JobBoard;
use App\Models\NightCrewJob;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class JobBoardTest extends TestCase
{
    use RefreshDatabase;

    /**
     * The board renders and shows existing jobs with their status columns.
     */
    public function test_renders_jobs_grouped_by_status(): void
    {
        NightCrewJob::factory()->forRepo('owner/Alpha')->create();
        NightCrewJob::factory()->forRepo('owner/Beta')->claimedBy('nas-01')->create();

        Livewire::test(JobBoard::class)
            ->assertOk()
            ->assertSee('owner/Alpha')
            ->assertSee('owner/Beta')
            ->assertSee('nas-01')
            ->assertSee('queued')
            ->assertSee('claimed');
    }

    /**
     * The add-job form creates a queued issue job.
     */
    public function test_add_job_creates_an_issue_job(): void
    {
        Livewire::test(JobBoard::class)
            ->set('repo', 'owner/Gamma')
            ->set('kind', 'issue')
            ->set('reference', '#7')
            ->call('addJob')
            ->assertHasNoErrors()
            ->assertSee('owner/Gamma');

        $this->assertDatabaseHas('night_crew_jobs', [
            'repo' => 'owner/Gamma',
            'kind' => JobKind::Issue->value,
            'reference' => '#7',
            'status' => JobStatus::Queued->value,
        ]);
    }

    /**
     * The add-job form creates a maintenance job with a cadence.
     */
    public function test_add_job_creates_a_maintenance_job(): void
    {
        Livewire::test(JobBoard::class)
            ->set('repo', 'owner/Delta')
            ->set('kind', 'maintenance')
            ->set('cadenceMinutes', 1440)
            ->call('addJob')
            ->assertHasNoErrors();

        $this->assertDatabaseHas('night_crew_jobs', [
            'repo' => 'owner/Delta',
            'kind' => JobKind::Maintenance->value,
            'cadence_minutes' => 1440,
        ]);
    }

    /**
     * An issue job requires a reference.
     */
    public function test_add_issue_job_requires_reference(): void
    {
        Livewire::test(JobBoard::class)
            ->set('repo', 'owner/Echo')
            ->set('kind', 'issue')
            ->set('reference', '')
            ->call('addJob')
            ->assertHasErrors('reference');

        $this->assertSame(0, NightCrewJob::query()->count());
    }

    /**
     * A maintenance job requires a cadence.
     */
    public function test_add_maintenance_job_requires_cadence(): void
    {
        Livewire::test(JobBoard::class)
            ->set('repo', 'owner/Foxtrot')
            ->set('kind', 'maintenance')
            ->call('addJob')
            ->assertHasErrors('cadenceMinutes');
    }

    /**
     * A repository is required.
     */
    public function test_repo_is_required(): void
    {
        Livewire::test(JobBoard::class)
            ->set('repo', '')
            ->set('reference', '#1')
            ->call('addJob')
            ->assertHasErrors('repo');
    }

    /**
     * The Echo handler re-renders the board with fresh data.
     */
    public function test_board_refreshes_when_a_job_event_arrives(): void
    {
        $component = Livewire::test(JobBoard::class)->assertDontSee('owner/Hotel');

        NightCrewJob::factory()->forRepo('owner/Hotel')->create();

        $component->call('onBoardChanged')->assertSee('owner/Hotel');
    }
}
