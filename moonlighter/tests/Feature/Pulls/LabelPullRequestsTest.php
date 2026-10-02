<?php

declare(strict_types=1);

namespace Tests\Feature\Pulls;

use App\Actions\Pulls\LabelPullRequests;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Client\ResponseSequence;
use Illuminate\Support\Facades\Http;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

final class LabelPullRequestsTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        config()->set('nightcrew.gitea.base_url', 'http://gitea.test');
        config()->set('nightcrew.gitea.token', 'test-token');
        config()->set('nightcrew.gitea.timeout', 5);
        config()->set('nightcrew.pull_labelling.repositories', ['owner/Demo']);
        config()->set('nightcrew.pull_labelling.page_size', 50);
        config()->set('nightcrew.pull_labelling.page_limit', 10);
        config()->set('nightcrew.pull_labelling.scaffold_paths', ['scripts/', 'docs/', '*.md']);
    }

    /**
     * Fake the Gitea endpoints one sweep of owner/Demo touches.
     *
     * @param  list<array<string, mixed>>  $pulls  Raw Gitea pull payloads.
     * @param  list<array<string, mixed>>|ResponseSequence  $files  The changed-file listing.
     * @param  list<array<string, mixed>>|null  $labels  Repository labels; null means the standard three.
     * @param  array  $comments
     *
     * @return void
     */
    private function fake(array $pulls, mixed $files = [], ?array $labels = null, array $comments = []): void
    {
        Http::fake([
            'http://gitea.test/api/v1/repos/owner/Demo/pulls?*' => Http::response($pulls),
            'http://gitea.test/api/v1/repos/owner/Demo/pulls/*/files*' => is_array($files) ? Http::response($files) : $files,
            'http://gitea.test/api/v1/repos/owner/Demo/labels*' => Http::response($labels === null ? [
                ['id' => 1, 'name' => 'review:requested'],
                ['id' => 2, 'name' => 'review:automerge'],
                ['id' => 3, 'name' => 'review:clean'],
            ] : $labels),
            'http://gitea.test/api/v1/repos/owner/Demo/issues/*/comments*' => Http::response($comments),
            // DELETE of one label is a different URL shape from POST of many;
            // the removal path is only exercised if both are faked.
            'http://gitea.test/api/v1/repos/owner/Demo/issues/*/labels/*' => Http::response([], 204),
            'http://gitea.test/api/v1/repos/owner/Demo/issues/*/labels' => Http::response([], 200),
        ]);
    }

    /**
     * A raw Gitea pull payload for an open crew PR, with overrides applied.
     *
     * @param  array<string, mixed>  $overrides
     *
     * @return array<string, mixed>
     */
    private function pull(array $overrides = []): array
    {
        return array_replace([
            'number' => 1,
            'title' => 'A pull request',
            'draft' => false,
            'user' => ['login' => 'author'],
            'head' => ['ref' => 'feature/2-scaffold-justfile', 'sha' => str_repeat('a', 40)],
            'base' => ['ref' => 'develop'],
            'labels' => [],
            'html_url' => 'http://gitea.test/owner/Demo/pulls/1',
        ], $overrides);
    }

    #[Test]
    public function it_requests_review_on_an_unlabelled_open_pull_request(): void
    {
        $this->fake([$this->pull()]);

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(1, $result['labelled']);
        $this->assertSame(0, $result['granted']);
    }

    #[Test]
    public function it_ignores_drafts_bots_and_human_held_pull_requests(): void
    {
        $this->fake([
            $this->pull(['number' => 1, 'draft' => true]),
            $this->pull(['number' => 2, 'user' => ['login' => 'dependabot[bot]']]),
            $this->pull(['number' => 3, 'labels' => [['name' => 'review:needs-human']]]),
            $this->pull(['number' => 4, 'labels' => [['name' => 'review:in-progress']]]),
        ]);

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(0, $result['labelled']);
        $this->assertSame(0, $result['granted']);
    }

    #[Test]
    public function it_grants_automerge_to_clean_crew_scaffold_work(): void
    {
        $this->fake(
            [$this->pull(['labels' => [['name' => 'review:clean']]])],
            [['filename' => 'scripts/tools/night_shift.sh'], ['filename' => 'docs/MERGE.md']],
        );

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(1, $result['granted']);
    }

    #[Test]
    public function it_refuses_automerge_when_the_diff_leaves_scaffold_paths(): void
    {
        // One behaviour-bearing file is enough to withhold the grant, even
        // though every other path is scaffold and the review came back clean.
        $this->fake(
            [$this->pull(['labels' => [['name' => 'review:clean']]])],
            [['filename' => 'docs/MERGE.md'], ['filename' => 'app/Models/Worker.php']],
        );

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(0, $result['granted']);
    }

    #[Test]
    public function it_refuses_automerge_on_a_branch_the_launcher_did_not_create(): void
    {
        // The launcher always creates feature/<issue>-<slug>. A hand-made branch
        // is a human's PR and never receives an automatic merge grant, however
        // harmless its diff looks.
        $this->fake(
            [$this->pull([
                'head' => ['ref' => 'chore/my-own-branch', 'sha' => str_repeat('b', 40)],
                'labels' => [['name' => 'review:clean']],
            ])],
            [['filename' => 'docs/MERGE.md']],
        );

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(0, $result['granted']);
    }

    #[Test]
    public function it_reads_every_page_of_changed_files_before_granting_automerge(): void
    {
        // Gitea caps a page at 50 files. A behaviour-bearing file on page two
        // must still withhold the grant.
        config()->set('nightcrew.pull_labelling.page_size', 2);

        $this->fake(
            [$this->pull(['labels' => [['name' => 'review:clean']]])],
            Http::sequence()
                ->push([['filename' => 'docs/A.md'], ['filename' => 'docs/B.md']])
                ->push([['filename' => 'app/Models/Worker.php']]),
        );

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(0, $result['granted']);
    }

    #[Test]
    public function it_refuses_automerge_when_the_file_list_is_truncated(): void
    {
        // Every page we may read is full, so more files may exist unseen. The
        // grant must fail closed rather than judge a partial diff.
        config()->set('nightcrew.pull_labelling.page_size', 2);
        config()->set('nightcrew.pull_labelling.page_limit', 2);

        $this->fake(
            [$this->pull(['labels' => [['name' => 'review:clean']]])],
            [['filename' => 'docs/A.md'], ['filename' => 'docs/B.md']],
        );

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(0, $result['granted']);
    }

    #[Test]
    public function file_entries_in_scaffold_paths_match_exactly_not_as_prefixes(): void
    {
        config()->set('nightcrew.pull_labelling.scaffold_paths', ['docs/', 'justfile']);

        $this->fake(
            [$this->pull(['labels' => [['name' => 'review:clean']]])],
            [['filename' => 'justfile'], ['filename' => 'justfile.d/anything.php']],
        );

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(0, $result['granted']);
    }

    #[Test]
    public function a_missing_label_is_reported_as_skipped_not_counted(): void
    {
        $this->fake([$this->pull()], [], [['id' => 3, 'name' => 'review:clean']]);

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(0, $result['labelled']);
        $this->assertSame(1, $result['skipped']);
        $this->assertSame('skipped', $result['repositories']['owner/Demo']['actions'][0]['kind']);
        Http::assertNotSent(static fn ($request): bool => $request->method() === 'POST');
    }

    #[Test]
    public function an_unreachable_repository_does_not_hide_the_others(): void
    {
        config()->set('nightcrew.pull_labelling.repositories', ['owner/Down', 'owner/Demo']);

        Http::fake([
            'http://gitea.test/api/v1/repos/owner/Down/pulls?*' => Http::response([], 503),
            'http://gitea.test/api/v1/repos/owner/Demo/pulls?*' => Http::response([$this->pull()]),
            'http://gitea.test/api/v1/repos/owner/Demo/labels*' => Http::response([['id' => 1, 'name' => 'review:requested']]),
            'http://gitea.test/api/v1/repos/owner/Demo/issues/*/labels' => Http::response([], 200),
        ]);

        $result = app(LabelPullRequests::class)->handle();

        $this->assertFalse($result['repositories']['owner/Down']['available']);
        $this->assertSame(1, $result['labelled']);
    }

    #[Test]
    public function a_star_entry_discovers_every_non_archived_repository(): void
    {
        // '*' must resolve fresh from Gitea, and must never sweep an archived
        // repository: those are read-only history, not work in flight.
        config()->set('nightcrew.pull_labelling.repositories', ['*']);

        Http::fake([
            'http://gitea.test/api/v1/user/repos?*' => Http::response([
                ['full_name' => 'owner/Demo', 'archived' => false],
                ['full_name' => 'owner/Old', 'archived' => true],
            ]),
            'http://gitea.test/api/v1/repos/owner/Demo/pulls?*' => Http::response([$this->pull()]),
            'http://gitea.test/api/v1/repos/owner/Demo/labels*' => Http::response([['id' => 1, 'name' => 'review:requested']]),
            'http://gitea.test/api/v1/repos/owner/Demo/issues/*/labels' => Http::response([], 200),
        ]);

        $result = app(LabelPullRequests::class)->handle();

        $this->assertArrayHasKey('owner/Demo', $result['repositories']);
        $this->assertArrayNotHasKey('owner/Old', $result['repositories']);
        $this->assertSame(1, $result['labelled']);
    }

    /** Build the hidden marker the review worker leaves on a PR comment. */
    private function reviewMarker(string $head, int $findings = 0): array
    {
        return [['body' => "## Automated review\n\n<!-- pulse-review:v1 head={$head} findings={$findings} -->"]];
    }

    #[Test]
    public function it_strips_a_verdict_once_the_head_moves_past_the_reviewed_commit(): void
    {
        $reviewed = str_repeat('c', 40);
        $current = str_repeat('d', 40);

        $this->fake(
            [$this->pull([
                'head' => ['ref' => 'feature/2-scaffold', 'sha' => $current],
                'labels' => [['name' => 'review:clean'], ['name' => 'review:automerge']],
            ])],
            [['filename' => 'docs/MERGE.md']],
            null,
            $this->reviewMarker($reviewed),
        );

        $result = app(LabelPullRequests::class)->handle();

        $this->assertTrue(
            $result['repositories']['owner/Demo']['available'],
            'sweep failed: '.json_encode($result['repositories']['owner/Demo']),
        );
        $this->assertSame(1, $result['refreshed']);
        $this->assertSame(0, $result['granted']);

        $action = $result['repositories']['owner/Demo']['actions'][0];
        $this->assertSame(['review:requested'], $action['add']);
        // The stale grant goes with the stale verdict: merge authority was
        // earned by a commit that is no longer the tip.
        $this->assertContains('review:automerge', $action['remove']);
        $this->assertContains('review:clean', $action['remove']);
    }

    #[Test]
    public function it_leaves_a_verdict_alone_while_the_head_still_matches(): void
    {
        $head = str_repeat('e', 40);

        $this->fake(
            [$this->pull([
                'head' => ['ref' => 'feature/2-scaffold', 'sha' => $head],
                'labels' => [['name' => 'review:clean'], ['name' => 'review:automerge']],
            ])],
            [['filename' => 'docs/MERGE.md']],
            null,
            $this->reviewMarker($head),
        );

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(0, $result['refreshed']);
    }

    #[Test]
    public function an_unmarked_verdict_is_never_stripped(): void
    {
        // A verdict a human applied by hand, or one predating markers, has no
        // marker to compare against. Missing evidence is not evidence of
        // staleness, so it is left exactly as the human left it.
        $this->fake(
            [$this->pull([
                'head' => ['ref' => 'chore/hand-made', 'sha' => str_repeat('f', 40)],
                'labels' => [['name' => 'review:clean']],
            ])],
            [['filename' => 'docs/MERGE.md']],
            null,
            [],
        );

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(0, $result['refreshed']);
        $this->assertSame(0, $result['labelled']);
    }

    /** Build the hidden marker the factory's review skill leaves on a PR comment. */
    private function factoryMarker(string $head, string $stage = 'review'): array
    {
        return [['body' => "## Automated review\n\n<!-- gitea-codex-{$stage}:v1 head={$head} base=".str_repeat('0', 40).' findings=0 -->']];
    }

    #[Test]
    public function it_grants_automerge_to_a_clear_review_on_crew_scaffold_work(): void
    {
        // review:clear is the factory's name for a clean verdict; it earns the
        // same grant the legacy review:clean label does.
        $this->fake(
            [$this->pull(['labels' => [['name' => 'review:clear']]])],
            [['filename' => 'scripts/tools/night_shift.sh'], ['filename' => 'docs/MERGE.md']],
        );

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(1, $result['granted']);
    }

    #[Test]
    public function it_strips_a_stale_clear_verdict_left_by_the_factory_review(): void
    {
        $reviewed = str_repeat('c', 40);
        $current = str_repeat('d', 40);

        $this->fake(
            [$this->pull([
                'head' => ['ref' => 'feature/2-scaffold', 'sha' => $current],
                'labels' => [['name' => 'review:clear'], ['name' => 'review:automerge']],
            ])],
            [['filename' => 'docs/MERGE.md']],
            null,
            $this->factoryMarker($reviewed),
        );

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(1, $result['refreshed']);

        $action = $result['repositories']['owner/Demo']['actions'][0];
        $this->assertSame(['review:requested'], $action['add']);
        $this->assertContains('review:clear', $action['remove']);
        $this->assertContains('review:automerge', $action['remove']);
    }

    #[Test]
    public function the_latest_marker_wins_across_both_marker_families(): void
    {
        // A legacy review of an older head, then a factory resolve marker for
        // the current head: the newer marker describes the tip, so the verdict
        // is current and must be left alone.
        $old = str_repeat('a', 40);
        $current = str_repeat('b', 40);

        $this->fake(
            [$this->pull([
                'head' => ['ref' => 'feature/2-scaffold', 'sha' => $current],
                'labels' => [['name' => 'review:clear'], ['name' => 'review:automerge']],
            ])],
            [['filename' => 'docs/MERGE.md']],
            null,
            array_merge($this->reviewMarker($old), $this->factoryMarker($current, 'resolve')),
        );

        $result = app(LabelPullRequests::class)->handle();

        $this->assertSame(0, $result['refreshed']);
    }
}
