<?php

declare(strict_types=1);

namespace Tests\Feature\Jobs;

use App\Enums\JobKind;
use App\Enums\JobStatus;
use App\Models\NightCrewJob;
use App\Models\Worker;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

class StoreJobTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Authenticate the test as a worker holding a token.
     */
    private function actingAsWorker(): Worker
    {
        $worker = Worker::factory()->create();
        Sanctum::actingAs($worker);

        return $worker;
    }

    /**
     * Intake rejects an unauthenticated request.
     */
    public function test_unauthenticated_request_is_rejected(): void
    {
        $this->postJson('/api/repos/owner/project/jobs', ['kind' => 'issue', 'reference' => '#5'])
            ->assertUnauthorized();

        $this->assertSame(0, NightCrewJob::query()->count());
    }

    /**
     * A valid issue job is persisted as queued for the repo named in the path.
     */
    public function test_creates_a_queued_issue_job_for_the_path_repo(): void
    {
        $this->actingAsWorker();

        $response = $this->postJson('/api/repos/owner/project/jobs', [
            'kind' => 'issue',
            'reference' => '#42',
            'priority' => 5,
        ]);

        $response->assertCreated();
        $response->assertJsonPath('data.repo', 'owner/project');
        $response->assertJsonPath('data.kind', 'issue');
        $response->assertJsonPath('data.status', 'queued');
        $response->assertJsonPath('data.priority', 5);

        $this->assertDatabaseHas('night_crew_jobs', [
            'repo' => 'owner/project',
            'kind' => JobKind::Issue->value,
            'reference' => '#42',
            'status' => JobStatus::Queued->value,
            'priority' => 5,
        ]);
    }

    /**
     * A valid maintenance job is persisted with its cadence and no reference.
     */
    public function test_creates_a_maintenance_job_with_cadence(): void
    {
        $this->actingAsWorker();

        $response = $this->postJson('/api/repos/owner/project/jobs', [
            'kind' => 'maintenance',
            'cadence_minutes' => 1440,
        ]);

        $response->assertCreated();
        $response->assertJsonPath('data.kind', 'maintenance');
        $response->assertJsonPath('data.cadence_minutes', 1440);
        $response->assertJsonPath('data.reference', null);
    }

    /**
     * kind is required.
     */
    public function test_validation_requires_kind(): void
    {
        $this->actingAsWorker();

        $this->postJson('/api/repos/owner/project/jobs', [])
            ->assertUnprocessable()
            ->assertJsonValidationErrors('kind');
    }

    /**
     * An issue job must carry a tracker reference.
     */
    public function test_issue_job_requires_a_reference(): void
    {
        $this->actingAsWorker();

        $this->postJson('/api/repos/owner/project/jobs', ['kind' => 'issue'])
            ->assertUnprocessable()
            ->assertJsonValidationErrors('reference');
    }

    /**
     * A maintenance job must carry a cadence and must not carry a reference.
     */
    public function test_maintenance_job_requires_cadence_and_forbids_reference(): void
    {
        $this->actingAsWorker();

        $this->postJson('/api/repos/owner/project/jobs', [
            'kind' => 'maintenance',
            'reference' => '#9',
        ])
            ->assertUnprocessable()
            ->assertJsonValidationErrors(['cadence_minutes', 'reference']);
    }

    /**
     * A maintenance job cannot be flagged contested.
     */
    public function test_maintenance_job_cannot_be_contested(): void
    {
        $this->actingAsWorker();

        $this->postJson('/api/repos/owner/project/jobs', [
            'kind' => 'maintenance',
            'cadence_minutes' => 60,
            'contested' => true,
        ])
            ->assertUnprocessable()
            ->assertJsonValidationErrors('contested');
    }
}
