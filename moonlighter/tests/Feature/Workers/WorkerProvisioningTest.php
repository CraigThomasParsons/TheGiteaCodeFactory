<?php

declare(strict_types=1);

namespace Tests\Feature\Workers;

use App\Models\User;
use App\Models\Worker;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class WorkerProvisioningTest extends TestCase
{
    use RefreshDatabase;

    /**
     * The command registers a worker with its served repos and mints a token.
     */
    public function test_command_registers_worker_and_mints_token(): void
    {
        $this->artisan('night-crew:worker:create', [
            'worker_id' => 'nas-01',
            '--repos' => 'owner/ExampleApp, owner/project',
        ])->assertExitCode(0);

        $worker = Worker::query()->where('worker_id', 'nas-01')->first();

        $this->assertNotNull($worker);
        $this->assertSame(
            ['owner/ExampleApp', 'owner/project'],
            $worker->served_repos,
        );
        $this->assertSame(1, $worker->tokens()->count());
    }

    /**
     * Re-registering an existing worker refreshes its repos, not its identity.
     */
    public function test_command_updates_existing_worker_repos(): void
    {
        $this->artisan('night-crew:worker:create', ['worker_id' => 'nas-01', '--repos' => 'owner/A'])->assertExitCode(0);
        $this->artisan('night-crew:worker:create', ['worker_id' => 'nas-01', '--repos' => 'owner/A,owner/B'])->assertExitCode(0);

        $this->assertSame(1, Worker::query()->where('worker_id', 'nas-01')->count());
        $worker = Worker::query()->where('worker_id', 'nas-01')->first();
        $this->assertSame(['owner/A', 'owner/B'], $worker->served_repos);
    }

    /**
     * A worker must serve at least one repository.
     */
    public function test_command_requires_at_least_one_repo(): void
    {
        $this->artisan('night-crew:worker:create', ['worker_id' => 'nas-01', '--repos' => '  ,  '])
            ->assertExitCode(1);

        $this->assertSame(0, Worker::query()->count());
    }

    /**
     * A valid worker token resolves to the worker's identity and served repos.
     */
    public function test_worker_me_returns_identity_for_valid_token(): void
    {
        $worker = Worker::factory()->serving(['owner/A', 'owner/B'])->create(['worker_id' => 'nas-01']);
        $plainTextToken = $worker->createToken('nas-01')->plainTextToken;

        $response = $this->withToken($plainTextToken)->getJson('/api/worker/me');

        $response->assertOk();
        $response->assertExactJson([
            'worker_id' => 'nas-01',
            'served_repos' => ['owner/A', 'owner/B'],
        ]);
    }

    /**
     * The endpoint rejects an unauthenticated request.
     */
    public function test_worker_me_rejects_unauthenticated_request(): void
    {
        $this->getJson('/api/worker/me')->assertUnauthorized();
    }

    /**
     * A token belonging to a non-worker (a human user) is refused by the resolver.
     */
    public function test_worker_me_rejects_non_worker_token(): void
    {
        $user = User::factory()->create();
        $plainTextToken = $user->createToken('human')->plainTextToken;

        $this->withToken($plainTextToken)->getJson('/api/worker/me')->assertForbidden();
    }
}
