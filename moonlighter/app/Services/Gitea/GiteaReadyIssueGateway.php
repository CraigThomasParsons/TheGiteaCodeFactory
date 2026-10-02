<?php

declare(strict_types=1);

namespace App\Services\Gitea;

use App\ValueObjects\ReadyGiteaIssue;
use Illuminate\Http\Client\PendingRequest;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\Http;
use RuntimeException;

/**
 * Read open, explicitly agent-ready issues from one Gitea repository.
 */
final class GiteaReadyIssueGateway
{
    /**
     * Fetch a bounded set of ready issues in deterministic issue-number order.
     *
     * @param  string  $repository  Canonical owner/name repository identifier.
     *
     * @return list<ReadyGiteaIssue>
     */
    public function fetch(string $repository): array
    {
        $this->assertConfigured();
        $issues = [];
        $pageLimit = (int) config('nightcrew.ready_intake.page_limit');
        $pageSize = (int) config('nightcrew.ready_intake.page_size');

        // Pagination is deliberately capped so one unhealthy or enormous
        // repository cannot turn a nightly intake into an unbounded operation.
        for ($page = 1; $page <= $pageLimit; $page++) {
            $response = $this->request()->get($this->issuesUrl($repository), [
                'state' => 'open',
                'type' => 'issues',
                'limit' => $pageSize,
                'page' => $page,
            ])->throw();

            /** @var list<array<string, mixed>> $pageIssues */
            $pageIssues = $response->json();
            $issues = [...$issues, ...$this->normalizeReadyIssues($repository, $pageIssues)];

            // A short page is Gitea's proof that no further request is needed.
            if (count($pageIssues) < $pageSize) {
                break;
            }
        }

        usort($issues, fn (ReadyGiteaIssue $left, ReadyGiteaIssue $right): int => $left->number <=> $right->number);

        return $issues;
    }

    /**
     * Build an authenticated, timeout-bounded Gitea request.
     */
    private function request(): PendingRequest
    {
        return Http::acceptJson()
            ->withToken((string) config('nightcrew.gitea.token'))
            ->timeout((int) config('nightcrew.gitea.timeout'));
    }

    /**
     * Reject an intake whose tracker credentials are not configured.
     */
    private function assertConfigured(): void
    {
        if (config('nightcrew.gitea.base_url') === '' || config('nightcrew.gitea.token') === '') {
            throw new RuntimeException('Gitea ready intake is not configured.');
        }
    }

    /**
     * Return the issue-list endpoint for one canonical repository.
     *
     * @param  string  $repository
     */
    private function issuesUrl(string $repository): string
    {
        return rtrim((string) config('nightcrew.gitea.base_url'), '/')
            .'/api/v1/repos/'.$repository.'/issues';
    }

    /**
     * Normalize only real issues carrying the exact readiness label.
     *
     * @param  string  $repository  Canonical owner/name repository identifier.
     * @param  list<array<string, mixed>>  $issues  Raw Gitea issue responses.
     *
     * @return list<ReadyGiteaIssue>
     */
    private function normalizeReadyIssues(string $repository, array $issues): array
    {
        $readyIssues = [];

        foreach ($issues as $issue) {
            // Gitea may return pull requests from the issues endpoint; PRs are
            // review evidence, never new implementation jobs. Gitea 1.26+ also
            // attaches "pull_request": null on ordinary issues — only a
            // non-empty value means this row is actually a PR.
            if ($this->isPullRequest($issue) || ! $this->hasReadyLabel($issue)) {
                continue;
            }

            $readyIssues[] = new ReadyGiteaIssue(
                repository: $repository,
                number: (int) Arr::get($issue, 'number'),
                title: (string) Arr::get($issue, 'title'),
                url: (string) Arr::get($issue, 'html_url'),
            );
        }

        return $readyIssues;
    }

    /**
     * True only when Gitea's pull_request field is a non-empty value.
     *
     * Null, false, and empty string/array are treated as "not a PR" so that
     * Gitea 1.26's null-keyed issue payloads remain eligible for intake.
     *
     * @param  array<string, mixed>  $issue  Raw Gitea issue response.
     */
    private function isPullRequest(array $issue): bool
    {
        if (! array_key_exists('pull_request', $issue)) {
            return false;
        }

        $pullRequest = $issue['pull_request'];

        if ($pullRequest === null || $pullRequest === false || $pullRequest === '') {
            return false;
        }

        if (is_array($pullRequest) && $pullRequest === []) {
            return false;
        }

        return true;
    }

    /**
     * Determine whether the issue carries the configured exact readiness label.
     *
     * @param  array<string, mixed>  $issue  Raw Gitea issue response.
     */
    private function hasReadyLabel(array $issue): bool
    {
        $readyLabel = (string) config('nightcrew.ready_intake.label');
        $labels = Arr::get($issue, 'labels', []);

        if (! is_array($labels)) {
            return false;
        }

        foreach ($labels as $label) {
            if (is_array($label) && Arr::get($label, 'name') === $readyLabel) {
                return true;
            }
        }

        return false;
    }
}
