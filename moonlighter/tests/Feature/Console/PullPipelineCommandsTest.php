<?php

declare(strict_types=1);

namespace Tests\Feature\Console;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Http;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

final class PullPipelineCommandsTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Point the Gitea gateway at a fake host.
     *
     * @return void
     */
    protected function setUp(): void
    {
        parent::setUp();

        config()->set('nightcrew.gitea.base_url', 'http://gitea.test');
        config()->set('nightcrew.gitea.token', 'test-token');
        config()->set('nightcrew.gitea.timeout', 5);
        config()->set('nightcrew.pull_labelling.page_size', 50);
        config()->set('nightcrew.pull_labelling.page_limit', 10);
    }

    /**
     * Release the frozen clock.
     *
     * @return void
     */
    protected function tearDown(): void
    {
        Carbon::setTestNow();
        parent::tearDown();
    }

    #[Test]
    public function schedule_active_exits_zero_inside_a_window(): void
    {
        // The seeded weekly rows open Mon to Fri 06:00 to 12:00 Toronto time.
        Carbon::setTestNow(Carbon::parse('2026-09-21 13:00:00', 'UTC')); // Mon 09:00 EDT

        $this->artisan('nightcrew:schedule-active')
            ->expectsOutput('active')
            ->assertExitCode(0);
    }

    #[Test]
    public function schedule_active_exits_one_outside_a_window(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-09-21 19:00:00', 'UTC')); // Mon 15:00 EDT

        $this->artisan('nightcrew:schedule-active')
            ->expectsOutput('outside-window')
            ->assertExitCode(1);
    }

    #[Test]
    public function schedule_active_quiet_output_prints_nothing(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-09-21 13:00:00', 'UTC'));

        $this->artisan('nightcrew:schedule-active', ['--quiet-output' => true])
            ->doesntExpectOutput('active')
            ->assertExitCode(0);
    }

    #[Test]
    public function list_pr_repos_prints_a_configured_list_as_given(): void
    {
        config()->set('nightcrew.pull_labelling.repositories', ['owner/One', 'owner/Two']);
        Http::fake();

        $this->artisan('nightcrew:list-pr-repos')
            ->expectsOutput('owner/One')
            ->expectsOutput('owner/Two')
            ->assertExitCode(0);

        Http::assertNothingSent();
    }

    #[Test]
    public function list_pr_repos_expands_a_star_to_every_non_archived_repository(): void
    {
        config()->set('nightcrew.pull_labelling.repositories', ['*']);

        Http::fake([
            'http://gitea.test/api/v1/user/repos?*' => Http::response([
                ['full_name' => 'owner/Demo', 'archived' => false],
                ['full_name' => 'owner/Old', 'archived' => true],
            ]),
        ]);

        $this->artisan('nightcrew:list-pr-repos')
            ->expectsOutput('owner/Demo')
            ->doesntExpectOutput('owner/Old')
            ->assertExitCode(0);
    }
}
