<?php

declare(strict_types=1);

namespace Tests\Feature\Jobs;

use App\Models\NightCrewJob;
use App\Models\Worker;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

/**
 * Exercise the authenticated Gitea-ready intake through its public HTTP door.
 */
class IntakeReadyGiteaIssuesTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Intake remains unavailable to callers without a worker token.
     */
    public function test_rejects_an_unauthenticated_scan(): void
    {
        $this->postJson('/api/intake/gitea-ready')->assertUnauthorized();

        $this->assertSame(0, NightCrewJob::query()->count());
    }

    /**
     * Ready issues become idempotent queue jobs while pull requests are ignored.
     */
    public function test_intakes_ready_issues_once_through_the_authenticated_door(): void
    {
        config()->set('nightcrew.gitea.base_url', 'http://gitea.test');
        config()->set('nightcrew.gitea.token', 'test-token');
        config()->set('nightcrew.ready_intake.repositories', ['owner/Portfolio']);

        // Gitea's issues endpoint can include pull requests, so the fixture
        // proves only real issues bearing the exact readiness label enter work.
        Http::fake([
            'http://gitea.test/api/v1/repos/owner/Portfolio/issues*' => Http::response([
                [
                    'number' => 26,
                    'title' => 'Adopt beads as in-repo agent tracker',
                    'html_url' => 'http://gitea.test/owner/Portfolio/issues/26',
                    'labels' => [['name' => 'ready-for-agent']],
                ],
                [
                    'number' => 27,
                    'title' => 'Not ready yet',
                    'html_url' => 'http://gitea.test/owner/Portfolio/issues/27',
                    'labels' => [['name' => 'needs-info']],
                ],
                [
                    'number' => 28,
                    'title' => 'A pull request response',
                    'html_url' => 'http://gitea.test/owner/Portfolio/pulls/28',
                    'labels' => [['name' => 'ready-for-agent']],
                    'pull_request' => ['merged' => false],
                ],
                // Gitea 1.26+ attaches a null pull_request key on ordinary issues.
                [
                    'number' => 29,
                    'title' => 'Ready issue with null pull_request key',
                    'html_url' => 'http://gitea.test/owner/Portfolio/issues/29',
                    'labels' => [['name' => 'ready-for-agent']],
                    'pull_request' => null,
                ],
            ]),
        ]);

        Sanctum::actingAs(Worker::factory()->create());

        $this->postJson('/api/intake/gitea-ready')
            ->assertOk()
            ->assertJsonPath('created', 2)
            ->assertJsonPath('existing', 0);

        // Repeating the scan must report the same tickets as existing rather
        // than manufacturing another claimable unit of work.
        $this->postJson('/api/intake/gitea-ready')
            ->assertOk()
            ->assertJsonPath('created', 0)
            ->assertJsonPath('existing', 2);

        $this->assertSame(2, NightCrewJob::query()->count());
        $this->assertDatabaseHas('night_crew_jobs', [
            'repo' => 'owner/Portfolio',
            'reference' => '#26',
            'source_key' => 'gitea:owner/Portfolio#26',
            'status' => 'queued',
        ]);
        $this->assertDatabaseHas('night_crew_jobs', [
            'repo' => 'owner/Portfolio',
            'reference' => '#29',
            'source_key' => 'gitea:owner/Portfolio#29',
            'status' => 'queued',
        ]);
        $this->assertDatabaseMissing('night_crew_jobs', [
            'reference' => '#28',
        ]);
    }

    /**
     * Null/false/empty pull_request markers stay eligible; a real PR object does not.
     */
    public function test_treats_only_non_empty_pull_request_as_a_pull_request(): void
    {
        config()->set('nightcrew.gitea.base_url', 'http://gitea.test');
        config()->set('nightcrew.gitea.token', 'test-token');
        config()->set('nightcrew.ready_intake.repositories', ['owner/Portfolio']);

        Http::fake([
            'http://gitea.test/api/v1/repos/owner/Portfolio/issues*' => Http::response([
                [
                    'number' => 101,
                    'title' => 'null pull_request',
                    'html_url' => 'http://gitea.test/owner/Portfolio/issues/101',
                    'labels' => [['name' => 'ready-for-agent']],
                    'pull_request' => null,
                ],
                [
                    'number' => 102,
                    'title' => 'false pull_request',
                    'html_url' => 'http://gitea.test/owner/Portfolio/issues/102',
                    'labels' => [['name' => 'ready-for-agent']],
                    'pull_request' => false,
                ],
                [
                    'number' => 103,
                    'title' => 'empty-string pull_request',
                    'html_url' => 'http://gitea.test/owner/Portfolio/issues/103',
                    'labels' => [['name' => 'ready-for-agent']],
                    'pull_request' => '',
                ],
                [
                    'number' => 104,
                    'title' => 'empty-array pull_request',
                    'html_url' => 'http://gitea.test/owner/Portfolio/issues/104',
                    'labels' => [['name' => 'ready-for-agent']],
                    'pull_request' => [],
                ],
                [
                    'number' => 105,
                    'title' => 'real pull request object',
                    'html_url' => 'http://gitea.test/owner/Portfolio/pulls/105',
                    'labels' => [['name' => 'ready-for-agent']],
                    'pull_request' => ['url' => 'http://gitea.test/owner/Portfolio/pulls/105', 'merged' => false],
                ],
            ]),
        ]);

        Sanctum::actingAs(Worker::factory()->create());

        $this->postJson('/api/intake/gitea-ready')
            ->assertOk()
            ->assertJsonPath('created', 4)
            ->assertJsonPath('repositories.owner/Portfolio.eligible', 4);

        foreach ([101, 102, 103, 104] as $number) {
            $this->assertDatabaseHas('night_crew_jobs', [
                'repo' => 'owner/Portfolio',
                'reference' => '#'.$number,
                'status' => 'queued',
            ]);
        }

        $this->assertDatabaseMissing('night_crew_jobs', [
            'reference' => '#105',
        ]);
    }

    /**
     * A failed repository is reported without suppressing healthy repositories.
     */
    public function test_retains_partial_repository_failure_evidence(): void
    {
        config()->set('nightcrew.gitea.base_url', 'http://gitea.test');
        config()->set('nightcrew.gitea.token', 'test-token');
        config()->set('nightcrew.ready_intake.repositories', [
            'owner/Unavailable',
            'owner/Healthy',
        ]);

        Http::fake([
            'http://gitea.test/api/v1/repos/owner/Unavailable/issues*' => Http::response([], 503),
            'http://gitea.test/api/v1/repos/owner/Healthy/issues*' => Http::response([
                [
                    'number' => 9,
                    'title' => 'Healthy ready work',
                    'html_url' => 'http://gitea.test/owner/Healthy/issues/9',
                    'labels' => [['name' => 'ready-for-agent']],
                ],
            ]),
        ]);

        Sanctum::actingAs(Worker::factory()->create());

        $this->postJson('/api/intake/gitea-ready')
            ->assertOk()
            ->assertJsonPath('created', 1)
            ->assertJsonPath('repositories.owner/Unavailable.available', false)
            ->assertJsonPath('repositories.owner/Healthy.available', true)
            ->assertJsonPath('repositories.owner/Healthy.eligible', 1);

        $this->assertDatabaseHas('night_crew_jobs', [
            'repo' => 'owner/Healthy',
            'reference' => '#9',
        ]);
    }
}
