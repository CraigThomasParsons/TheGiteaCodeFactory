<?php

declare(strict_types=1);

namespace App\Actions\Jobs;

use App\Enums\JobKind;
use App\Enums\JobStatus;
use App\Events\JobCreated;
use App\Models\NightCrewJob;
use Illuminate\Support\Arr;

/**
 * Persist a validated job submission as a queued NightCrewJob.
 */
final class CreateJobAction
{
    /**
     * Create a queued job for the given repository from validated intake data.
     *
     * Fields are assigned directly rather than mass-assigned: this is trusted
     * internal code, and it lets us set the queued status (which intake must not
     * be able to choose) and fully populate the returned model without relying
     * on database defaults.
     *
     * @param  string  $repo  The repository the job belongs to.
     * @param  array<string, mixed>  $validated  Validated intake attributes.
     */
    public function handle(string $repo, array $validated): NightCrewJob
    {
        if ($validated['kind'] === JobKind::PullRequest->value) {
            return $this->pullRequest($repo, $validated);
        }
        $job = new NightCrewJob;

        $job->repo = $repo;
        $job->kind = JobKind::from($validated['kind']);
        $job->reference = Arr::get($validated, 'reference');
        $job->payload = Arr::get($validated, 'payload');
        $job->priority = (int) Arr::get($validated, 'priority', 0);
        $job->contested = (bool) Arr::get($validated, 'contested', false);
        $job->cadence_minutes = Arr::get($validated, 'cadence_minutes');

        // A new job is queued and workable immediately; the claim and status
        // slices move next_due_at forward for recurring maintenance.
        $job->status = JobStatus::Queued;
        $job->next_due_at = now();

        $job->save();

        // Tell the live dashboard a job just landed on the board.
        JobCreated::dispatch($job);

        return $job;
    }

    /**
     * Admit a PR revision/stage once; repeat discovery cannot reset its claim.
     *
     * @param  string  $repo
     * @param  array<string, mixed>  $validated
     */
    private function pullRequest(string $repo, array $validated): NightCrewJob
    {
        $payload = $validated['payload'];
        $sourceKey = 'pr:'.hash('sha256', implode(':', [
            $repo, $validated['reference'], $payload['head'], $payload['base'], $payload['stage'], $payload['attempt'],
        ]));
        $job = NightCrewJob::query()->firstOrCreate(['source_key' => $sourceKey], [
            'repo' => $repo, 'kind' => JobKind::PullRequest, 'reference' => $validated['reference'],
            'payload' => $payload, 'priority' => 0, 'contested' => false,
            'next_due_at' => now(),
        ]);
        if ($job->wasRecentlyCreated) {
            // Database defaults are not hydrated into a model inserted through
            // firstOrCreate. Refresh before broadcasting or returning it so the
            // queued status is always represented by its enum cast.
            $job->refresh();
            JobCreated::dispatch($job);
        } elseif ($job->status === JobStatus::Failed) {
            // Rediscovery retries the same immutable stage without creating a
            // duplicate row. Its previous receipt remains as failure evidence.
            $job->status = JobStatus::Queued;
            $job->worker_id = null;
            $job->claimed_by = null;
            $job->claimed_at = null;
            $job->claim_token = null;
            $job->next_due_at = now();
            $job->save();
        }

        return $job;
    }
}
