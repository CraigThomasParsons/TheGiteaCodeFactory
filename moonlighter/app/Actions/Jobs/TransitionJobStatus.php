<?php

declare(strict_types=1);

namespace App\Actions\Jobs;

use App\Enums\JobKind;
use App\Enums\JobStatus;
use App\Events\JobStatusChanged;
use App\Models\NightCrewJob;
use App\Models\Worker;
use App\Services\Gitea\GiteaFence;
use Illuminate\Auth\Access\AuthorizationException;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\ValidationException;

/**
 * Move a job through its lifecycle as a worker reports progress.
 *
 * The legal path is claimed -> running -> done|failed. A done maintenance job
 * recurs (it returns to the queue with its next due time advanced); every other
 * terminal transition leaves the job in its reported state.
 */
final class TransitionJobStatus
{
    public function __construct(private GiteaFence $fence) {}

    /**
     * Allowed target statuses keyed by the current status.
     *
     * @var array<string, array<int, JobStatus>>
     */
    private const TRANSITIONS = [
        'claimed' => [JobStatus::Running],
        'running' => [JobStatus::Done, JobStatus::Failed],
    ];

    /**
     * Apply a reported status change for the given worker.
     *
     * @param  NightCrewJob  $job
     * @param  Worker  $worker
     * @param  JobStatus  $target
     * @param  array  $receipt
     * @param  ?string  $claimToken
     *
     * @throws AuthorizationException When the worker does not hold the job.
     * @throws ValidationException When the transition is not legal.
     */
    public function handle(NightCrewJob $job, Worker $worker, JobStatus $target, array $receipt = [], ?string $claimToken = null): NightCrewJob
    {
        $transitionedJob = DB::transaction(function () use ($job, $worker, $target, $receipt, $claimToken): NightCrewJob {
            // Re-read under a lock so a concurrent transition cannot interleave.
            $lockedJob = NightCrewJob::query()->lockForUpdate()->findOrFail($job->getKey());

            $this->assertWorkerMayTransition($lockedJob, $worker);
            if ($lockedJob->kind === JobKind::PullRequest) {
                abort_unless($claimToken !== null && hash_equals((string) $lockedJob->claim_token, $claimToken), 403);
                if ($target === $lockedJob->status) {
                    $lockedJob->claimed_at = now();
                    $lockedJob->receipt = $receipt;
                    $lockedJob->save();

                    return $lockedJob;
                }
                if ($target === JobStatus::Queued && in_array($lockedJob->status, [JobStatus::Claimed, JobStatus::Running], true)) {
                    $lockedJob->status = JobStatus::Queued;
                    $lockedJob->worker_id = null;
                    $lockedJob->claimed_by = null;
                    $lockedJob->claimed_at = null;
                    $lockedJob->claim_token = null;
                    $lockedJob->receipt = $receipt;
                    $lockedJob->save();

                    return $lockedJob;
                }
                $lockedJob->receipt = $receipt;
            }
            $this->assertTransitionAllowed($lockedJob->status, $target);

            $this->applyTransition($lockedJob, $target);
            $lockedJob->save();

            return $lockedJob;
        });

        // Broadcast the change to the live dashboard once it is committed.
        JobStatusChanged::dispatch($transitionedJob);

        // Fence a finished issue onto its Gitea ticket (best-effort, post-commit).
        if ($target === JobStatus::Done && $transitionedJob->kind === JobKind::Issue) {
            $this->fence->markDone($transitionedJob->repo, $transitionedJob->reference);
        }

        return $transitionedJob;
    }

    /**
     * Only the holding worker may transition a job. For a contested issue job,
     * any of the racing workers may; for every other job, just the claimer.
     *
     * @param  NightCrewJob  $job
     * @param  Worker  $worker
     *
     * @throws AuthorizationException
     */
    private function assertWorkerMayTransition(NightCrewJob $job, Worker $worker): void
    {
        if ($job->contested) {
            if (in_array($worker->worker_id, $job->claimers(), true) === false) {
                throw new AuthorizationException('This worker has not claimed the job.');
            }

            return;
        }

        if ($job->worker_id !== $worker->worker_id) {
            throw new AuthorizationException('This worker has not claimed the job.');
        }
    }

    /**
     * The reported target must be reachable from the job's current status.
     *
     * @param  JobStatus  $current
     * @param  JobStatus  $target
     *
     * @throws ValidationException
     */
    private function assertTransitionAllowed(JobStatus $current, JobStatus $target): void
    {
        $allowedTargets = array_key_exists($current->value, self::TRANSITIONS)
            ? self::TRANSITIONS[$current->value]
            : [];

        if (in_array($target, $allowedTargets, true) === false) {
            throw ValidationException::withMessages([
                'status' => "Cannot move a {$current->value} job to {$target->value}.",
            ]);
        }
    }

    /**
     * Write the new status, recurring maintenance jobs instead of terminating.
     *
     * @param  NightCrewJob  $job
     * @param  JobStatus  $target
     */
    private function applyTransition(NightCrewJob $job, JobStatus $target): void
    {
        // A finished maintenance job is not done forever: it records this run and
        // returns to the queue, due again one cadence from now, free to re-claim.
        if ($target === JobStatus::Done && $job->kind === JobKind::Maintenance) {
            $job->last_run_at = now();
            $job->next_due_at = now()->addMinutes($job->cadence_minutes);
            $job->status = JobStatus::Queued;
            $job->worker_id = null;
            $job->claimed_at = null;
            $job->claimed_by = null;

            return;
        }

        $job->status = $target;
    }
}
