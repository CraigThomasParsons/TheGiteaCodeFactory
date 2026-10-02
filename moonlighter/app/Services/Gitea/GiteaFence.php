<?php

declare(strict_types=1);

namespace App\Services\Gitea;

use Illuminate\Http\Client\PendingRequest;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

/**
 * Reflects a job's claim onto its Gitea issue — the human-visible fence behind
 * which the real lock sits.
 *
 * Every call is best-effort: the fence is never the lock. When Gitea is not
 * configured the fence is inert, and any Gitea failure is logged and swallowed
 * so it can never roll back or block a claim.
 */
final class GiteaFence
{
    /**
     * Whether the fence is configured and should talk to Gitea at all.
     */
    public function enabled(): bool
    {
        return $this->baseUrl() !== '' && $this->token() !== '';
    }

    /**
     * Whether a human (anyone other than the crew bot) already holds the issue —
     * assigned to it, or having marked it in-progress. On any uncertainty
     * (disabled, unparseable reference, Gitea unreachable) this returns false so
     * the crew is never blocked by the fence.
     *
     * @param  string  $repo  The owner/name repository.
     * @param  string|null  $reference  The issue reference, e.g. "#42".
     */
    public function issueHeldByHuman(string $repo, ?string $reference): bool
    {
        $index = $this->issueIndex($reference);

        if ($this->enabled() === false || $index === null) {
            return false;
        }

        $heldByHuman = false;

        $this->safe(function () use ($repo, $index, &$heldByHuman): void {
            $response = $this->request()->get($this->issueUrl($repo, $index));

            // If we cannot read the issue we cannot claim it is human-held, so we
            // leave the crew free to proceed.
            if ($response->successful() === false) {
                return;
            }

            $issue = $response->json();
            $assignees = $this->assigneeLogins($issue);
            $labels = $this->labelNames($issue);

            $botHolds = in_array($this->bot(), $assignees, true);
            $humanAssigned = count(array_filter($assignees, fn (string $login): bool => $login !== $this->bot())) > 0;
            $inProgress = in_array($this->label('in_progress'), $labels, true);

            $heldByHuman = ($humanAssigned || $inProgress) && $botHolds === false;
        });

        return $heldByHuman;
    }

    /**
     * Fence a freshly claimed issue: assign the crew bot, mark it in-progress,
     * and leave an [Agent Start] comment.
     *
     * @param  string  $repo  The owner/name repository.
     * @param  string|null  $reference  The issue reference, e.g. "#42".
     * @param  string  $workerId  The worker that claimed the job.
     */
    public function markClaimed(string $repo, ?string $reference, string $workerId): void
    {
        $index = $this->issueIndex($reference);

        if ($this->enabled() === false || $index === null) {
            return;
        }

        $issueUrl = $this->issueUrl($repo, $index);

        $this->safe(function () use ($issueUrl, $workerId): void {
            $this->request()->patch($issueUrl, ['assignees' => [$this->bot()]]);
            $this->request()->post($issueUrl.'/labels', ['labels' => [$this->label('in_progress')]]);
            $this->request()->post($issueUrl.'/comments', [
                'body' => "[Agent Start] Claimed by night-crew worker `{$workerId}`.",
            ]);
        });
    }

    /**
     * Fence a finished issue: mark it complete, comment, and close it.
     *
     * @param  string  $repo  The owner/name repository.
     * @param  string|null  $reference  The issue reference, e.g. "#42".
     */
    public function markDone(string $repo, ?string $reference): void
    {
        $index = $this->issueIndex($reference);

        if ($this->enabled() === false || $index === null) {
            return;
        }

        $issueUrl = $this->issueUrl($repo, $index);

        $this->safe(function () use ($issueUrl): void {
            $this->request()->post($issueUrl.'/labels', ['labels' => [$this->label('complete')]]);
            $this->request()->post($issueUrl.'/comments', [
                'body' => '[Agent Done] Completed by the night crew.',
            ]);
            $this->request()->patch($issueUrl, ['state' => 'closed']);
        });
    }

    /**
     * Run a Gitea operation, logging and swallowing any failure so the fence can
     * never break the caller.
     *
     * @param  callable  $operation
     */
    private function safe(callable $operation): void
    {
        try {
            $operation();
        } catch (\Throwable $failure) {
            Log::warning('night-crew gitea fence failed', ['error' => $failure->getMessage()]);
        }
    }

    /**
     * A pre-configured, authenticated, timeout-bounded HTTP request to Gitea.
     */
    private function request(): PendingRequest
    {
        return Http::withHeaders(['Authorization' => 'token '.$this->token()])
            ->timeout($this->timeout())
            ->acceptJson();
    }

    /**
     * The assignee logins on an issue payload.
     *
     * @param  mixed  $issue
     *
     * @return array<int, string>
     */
    private function assigneeLogins(mixed $issue): array
    {
        $assignees = Arr::get($issue, 'assignees');
        $assignees = is_array($assignees) ? $assignees : [];

        return array_values(array_filter(array_map(
            fn (mixed $assignee): string => (string) Arr::get($assignee, 'login', ''),
            $assignees,
        )));
    }

    /**
     * The label names on an issue payload.
     *
     * @param  mixed  $issue
     *
     * @return array<int, string>
     */
    private function labelNames(mixed $issue): array
    {
        $labels = Arr::get($issue, 'labels');
        $labels = is_array($labels) ? $labels : [];

        return array_map(
            fn (mixed $label): string => (string) Arr::get($label, 'name', ''),
            $labels,
        );
    }

    /**
     * Parse the numeric issue index from a reference like "#42".
     *
     * @param  ?string  $reference
     */
    private function issueIndex(?string $reference): ?int
    {
        if ($reference === null) {
            return null;
        }

        $digits = preg_replace('/\D+/', '', $reference);

        if ($digits === null || $digits === '') {
            return null;
        }

        return (int) $digits;
    }

    /**
     * The full Gitea API URL for an issue.
     *
     * @param  string  $repo
     * @param  int  $index
     */
    private function issueUrl(string $repo, int $index): string
    {
        return rtrim($this->baseUrl(), '/')."/repos/{$repo}/issues/{$index}";
    }

    /**
     * The configured Gitea API base URL.
     */
    private function baseUrl(): string
    {
        return (string) config('nightcrew.gitea.base_url', '');
    }

    /**
     * The configured Gitea API token.
     */
    private function token(): string
    {
        return (string) config('nightcrew.gitea.token', '');
    }

    /**
     * The crew bot account login.
     */
    private function bot(): string
    {
        return (string) config('nightcrew.gitea.bot', '');
    }

    /**
     * The request timeout in seconds.
     */
    private function timeout(): int
    {
        return (int) config('nightcrew.gitea.timeout', 5);
    }

    /**
     * A configured label name by key (in_progress or complete).
     *
     * @param  string  $key
     */
    private function label(string $key): string
    {
        return (string) config("nightcrew.gitea.labels.{$key}", '');
    }
}
