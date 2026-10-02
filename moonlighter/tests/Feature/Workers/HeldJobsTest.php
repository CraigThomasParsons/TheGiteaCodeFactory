<?php

declare(strict_types=1);

namespace Tests\Feature\Workers;

use App\Enums\JobKind;
use App\Models\NightCrewJob;
use App\Models\User;
use App\Models\Worker;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

/**
 * The read-only held-jobs endpoint a local bridge uses to reconcile its durable
 * ledger with the coordinator's claims after a restart or a lost response.
 */
class HeldJobsTest extends TestCase
{
    use RefreshDatabase;

    private const REPO = 'owner/project';

    /**
     * Listing held jobs requires authentication.
     */
    public function test_unauthenticated_request_is_rejected(): void
    {
        $this->getJson('/api/worker/jobs')->assertUnauthorized();
    }

    /**
     * A non-worker token must not reach a worker-only endpoint.
     */
    public function test_non_worker_token_is_forbidden(): void
    {
        Sanctum::actingAs(User::factory()->create());

        $this->getJson('/api/worker/jobs')->assertForbidden();
    }

    /**
     * Only the caller's own claimed or running jobs are listed; queued, finished
     * and other workers' jobs are not.
     */
    public function test_lists_only_the_workers_own_active_claims(): void
    {
        $worker = Worker::factory()->serving([self::REPO])->create(['worker_id' => 'nas-01']);
        Sanctum::actingAs($worker);
        $claimed = NightCrewJob::factory()->forRepo(self::REPO)->claimedBy('nas-01')->create();
        $running = NightCrewJob::factory()->forRepo(self::REPO)->runningBy('nas-01')->create();
        NightCrewJob::factory()->forRepo(self::REPO)->claimedBy('nas-02')->create();
        NightCrewJob::factory()->forRepo(self::REPO)->create();
        NightCrewJob::factory()->forRepo(self::REPO)->done()->create(['worker_id' => 'nas-01']);

        $response = $this->getJson('/api/worker/jobs');

        $response->assertOk()
            ->assertJsonCount(2, 'data')
            ->assertJsonPath('data.0.id', $claimed->id)
            ->assertJsonPath('data.0.status', 'claimed')
            ->assertJsonPath('data.0.worker_id', 'nas-01')
            ->assertJsonPath('data.1.id', $running->id)
            ->assertJsonPath('data.1.status', 'running');
        $this->assertNotNull($response->json('data.0.claimed_at'));
    }

    /**
     * A PR job's claim fence is returned to its holder so it can resume after a
     * restart, and the endpoint never changes coordinator state.
     */
    public function test_returns_own_claim_token_and_is_read_only(): void
    {
        $worker = Worker::factory()->serving([self::REPO])->create(['worker_id' => 'nas-01']);
        Sanctum::actingAs($worker);
        $job = NightCrewJob::factory()->forRepo(self::REPO)->claimedBy('nas-01')->create([
            'kind' => JobKind::PullRequest,
            'reference' => '26',
        ]);
        $job->forceFill(['claim_token' => 'fence-token-uuid'])->save();
        $before = $job->fresh()->toArray();

        $this->getJson('/api/worker/jobs')
            ->assertOk()
            ->assertJsonPath('data.0.claim_token', 'fence-token-uuid');

        $this->assertSame($before, $job->fresh()->toArray());
    }
}
