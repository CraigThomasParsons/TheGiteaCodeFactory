<?php

declare(strict_types=1);

namespace App\Services\Gitea;

use Illuminate\Http\Client\PendingRequest;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\Http;
use RuntimeException;

/**
 * Read pull requests and mutate their labels on Gitea.
 *
 * Deliberately separate from GiteaReadyIssueGateway: that one admits *issues*
 * as work, this one observes *pull requests* already in flight. They share a
 * host and a token and nothing else.
 */
final class GiteaPullRequestGateway
{
    /**
     * The repositories the PR pipeline may touch.
     *
     * A single '*' entry means "every non-archived repository this token can
     * see", resolved fresh each run so a new repository needs no config edit.
     * Both the labelling sweep and the shell stages ask here, so the expansion
     * lives in exactly one place.
     *
     * @return list<string>
     */
    public function pipelineRepositories(): array
    {
        /** @var list<string> $configured */
        $configured = config('nightcrew.pull_labelling.repositories');

        if (in_array('*', $configured, true)) {
            return $this->allRepositories();
        }

        return $configured;
    }

    /**
     * Every non-archived repository this token can see.
     *
     * Discovery rather than a static list: a repository created tomorrow is
     * enrolled tomorrow, with no config edit and no silent gap between "the
     * repo exists" and "the pipeline knows about it".
     *
     * @return list<string>
     */
    public function allRepositories(): array
    {
        $this->assertConfigured();

        $names = [];
        $listing = $this->paginate(rtrim((string) config('nightcrew.gitea.base_url'), '/').'/api/v1/user/repos');

        foreach ($listing['items'] as $repository) {
            if (is_array($repository) && Arr::get($repository, 'archived', false) === false) {
                $names[] = (string) Arr::get($repository, 'full_name');
            }
        }

        sort($names);

        return array_values(array_unique(array_filter($names)));
    }

    /**
     * Every open pull request in one repository, normalised.
     *
     * @param  string  $repository
     *
     * @return list<array<string, mixed>>
     */
    public function openPullRequests(string $repository): array
    {
        $this->assertConfigured();

        $listing = $this->paginate($this->url($repository, 'pulls'), ['state' => 'open']);

        return array_map(fn (mixed $pull): array => $this->normalise($pull), $listing['items']);
    }

    /**
     * The commit a completed review or resolve last reported on, or null when
     * no marker is present.
     *
     * The review and resolve workers each end their posted comment with a
     * hidden marker naming the exact head they acted on. That marker, not the
     * label, is the record of what was actually looked at: a label survives a
     * force-push, a rebase and three more commits, and says nothing about which
     * of them anyone read.
     *
     * @param  string  $repository  Canonical owner/name repository identifier.
     * @param  int  $number  Pull request number.
     *
     * @return string|null 40-character SHA, or null when unmarked.
     */
    public function reviewedHead(string $repository, int $number): ?string
    {
        $this->assertConfigured();

        $comments = $this->request()
            ->get($this->url($repository, "issues/{$number}/comments"), ['limit' => 100])
            ->throw()
            ->json();

        if (! is_array($comments)) {
            return null;
        }

        $head = null;

        // Last marker wins: a resolve push supersedes the review before it.
        // Both marker families count: gitea-codex-* from the factory's skills
        // and the older pulse-* from earlier review workers.
        foreach ($comments as $comment) {
            $body = '';

            if (is_array($comment) && array_key_exists('body', $comment)) {
                $body = (string) $comment['body'];
            }

            if (preg_match('/<!--\s*(?:gitea-codex|pulse)-(?:review|resolve):v1\s+head=([0-9a-f]{40})/', $body, $matches) === 1) {
                $head = $matches[1];
            }
        }

        return $head;
    }

    /**
     * The paths a pull request changes. Used to decide whether it is confined
     * to scaffold territory.
     *
     * Fails closed: when the file list is longer than the page limit allows us
     * to read, an empty list comes back, because judging scaffold scope on a
     * truncated diff could grant merge authority to an unseen file.
     *
     * @param  string  $repository
     * @param  int  $number
     *
     * @return list<string>
     */
    public function changedPaths(string $repository, int $number): array
    {
        $this->assertConfigured();

        $listing = $this->paginate($this->url($repository, "pulls/{$number}/files"));

        if ($listing['complete'] === false) {
            return [];
        }

        return array_values(array_filter(array_map(
            static fn (mixed $file): string => is_array($file) ? (string) Arr::get($file, 'filename', '') : '',
            $listing['items'],
        )));
    }

    /**
     * Add labels (by id) to one pull request. A no-op for an empty list.
     *
     * @param  string  $repository
     * @param  int  $number
     * @param  list<int>  $labelIds
     *
     * @return void
     */
    public function addLabels(string $repository, int $number, array $labelIds): void
    {
        if ($labelIds === []) {
            return;
        }

        $this->request()
            ->post($this->url($repository, "issues/{$number}/labels"), ['labels' => array_values($labelIds)])
            ->throw();
    }

    /**
     * Remove one label (by id) from one pull request.
     *
     * @param  string  $repository
     * @param  int  $number
     * @param  int  $labelId
     *
     * @return void
     */
    public function removeLabel(string $repository, int $number, int $labelId): void
    {
        $this->request()
            ->delete($this->url($repository, "issues/{$number}/labels/{$labelId}"))
            ->throw();
    }

    /**
     * Label name => id for one repository.
     *
     * @param  string  $repository
     *
     * @return array<string, int>
     */
    public function labelIds(string $repository): array
    {
        $map = [];

        foreach ($this->paginate($this->url($repository, 'labels'))['items'] as $label) {
            if (is_array($label) && isset($label['name'], $label['id'])) {
                $map[(string) $label['name']] = (int) $label['id'];
            }
        }

        return $map;
    }

    /**
     * Read every page of a Gitea list endpoint, up to the configured page limit.
     *
     * Gitea caps page size server side, so a single request silently truncates
     * any list longer than one page. `complete` is false when the last page we
     * were allowed to read was still full, meaning more items may exist.
     *
     * @param  string  $url
     * @param  array<string, mixed>  $query
     *
     * @return array{items: list<mixed>, complete: bool}
     */
    private function paginate(string $url, array $query = []): array
    {
        $items = [];
        $pageLimit = (int) config('nightcrew.pull_labelling.page_limit');
        $pageSize = (int) config('nightcrew.pull_labelling.page_size');

        for ($page = 1; $page <= $pageLimit; $page++) {
            $batch = $this->request()
                ->get($url, $query + ['limit' => $pageSize, 'page' => $page])
                ->throw()
                ->json();

            if (! is_array($batch)) {
                throw new RuntimeException("Unexpected list response from {$url}.");
            }

            array_push($items, ...array_values($batch));

            if (count($batch) < $pageSize) {
                return ['items' => $items, 'complete' => true];
            }
        }

        return ['items' => $items, 'complete' => false];
    }

    /**
     * @param  mixed  $pull
     *
     * @return array<string, mixed>
     */
    private function normalise(mixed $pull): array
    {
        return [
            'number' => (int) Arr::get($pull, 'number'),
            'title' => (string) Arr::get($pull, 'title', ''),
            'draft' => (bool) Arr::get($pull, 'draft', false),
            'author' => (string) Arr::get($pull, 'user.login', ''),
            'head_ref' => (string) Arr::get($pull, 'head.ref', ''),
            'head_sha' => (string) Arr::get($pull, 'head.sha', ''),
            'base_ref' => (string) Arr::get($pull, 'base.ref', ''),
            'labels' => array_values(array_map(
                static fn (mixed $label): string => (string) Arr::get($label, 'name', ''),
                (array) Arr::get($pull, 'labels', []),
            )),
            'url' => (string) Arr::get($pull, 'html_url', ''),
        ];
    }

    /**
     * An authenticated JSON request to Gitea.
     *
     * @return PendingRequest
     */
    private function request(): PendingRequest
    {
        return Http::acceptJson()
            ->withToken((string) config('nightcrew.gitea.token'))
            ->timeout((int) config('nightcrew.gitea.timeout'));
    }

    /**
     * The API URL for one repository-scoped endpoint.
     *
     * @param  string  $repository
     * @param  string  $suffix
     *
     * @return string
     */
    private function url(string $repository, string $suffix): string
    {
        return rtrim((string) config('nightcrew.gitea.base_url'), '/')
            ."/api/v1/repos/{$repository}/{$suffix}";
    }

    /**
     * Refuse to talk to Gitea without a host and a token.
     *
     * @return void
     *
     * @throws RuntimeException
     */
    private function assertConfigured(): void
    {
        if (config('nightcrew.gitea.base_url') === '' || config('nightcrew.gitea.token') === '') {
            throw new RuntimeException('Gitea pull-request labelling is not configured.');
        }
    }
}
