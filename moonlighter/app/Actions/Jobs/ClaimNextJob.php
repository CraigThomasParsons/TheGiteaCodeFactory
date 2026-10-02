<?php

declare(strict_types=1);

namespace App\Actions\Jobs;

use App\Enums\JobKind;
use App\Enums\JobStatus;
use App\Events\JobClaimed;
use App\Models\NightCrewJob;
use App\Models\Worker;
use App\Services\Gitea\GiteaFence;
use App\Services\Schedule;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Collection;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

/**
 * Atomically hand a worker the next job it should run.
 *
 * This is the single source of truth for "who works what." Claiming is gated by
 * Schedule::isActive (fail-closed outside the window). The selection runs inside
 * a transaction with a row lock so two workers can never both claim the same
 * non-contested job.
 */
final class ClaimNextJob
{
    /**
     * Inject the Gitea fence and the claiming schedule gate.
     *
     * @param  GiteaFence  $fence  Checks a job is still claimable on Gitea.
     * @param  Schedule  $schedule  Fail-closed gate on the crew's active hours.
     */
    public function __construct(
        private GiteaFence $fence,
        private Schedule $schedule,
    ) {}

    /**
     * Claim and return the highest-priority due job for the worker, or null when
     * nothing is actionable for the repositories it serves.
     *
     * @param  Worker  $worker
     * @param  ?string  $stage
     * @param  bool  $recoverStale
     */
    public function forWorker(Worker $worker, ?string $stage = null, bool $recoverStale = false): ?NightCrewJob
    {
        // Outside the crew schedule, claim quietly returns nothing (fail-closed).
        if ($this->schedule->isActive() === false) {
            return null;
        }

        $claimedJob = DB::transaction(function () use ($worker, $stage, $recoverStale): ?NightCrewJob {
            Worker::query()->orderBy('id')->lockForUpdate()->get();
            if ($stage !== null) {
                // Serialize PR claims across all workers, not just one host.
                if ($recoverStale) {
                    // The local adapter requests this only while holding its OS
                    // lock. Recovery is limited to the same stable worker ID;
                    // another machine can never steal an old writer's lease.
                    NightCrewJob::query()->where('kind', JobKind::PullRequest)
                        ->whereIn('status', [JobStatus::Claimed, JobStatus::Running])
                        ->where('worker_id', $worker->worker_id)
                        ->where('claimed_at', '<', now()->subMinutes(15))
                        ->update(['status' => JobStatus::Queued->value, 'worker_id' => null,
                            'claimed_by' => null, 'claimed_at' => null, 'claim_token' => null]);
                }
                if (NightCrewJob::query()->where('kind', JobKind::PullRequest)
                    ->whereIn('status', [JobStatus::Claimed, JobStatus::Running])->exists()) {
                    return null;
                }
            }
            $candidates = $this->candidatesFor($worker, $stage);

            // Candidates are already ordered highest-priority-first; take the
            // first one this worker is actually allowed to claim.
            foreach ($candidates as $candidate) {
                if ($this->isClaimableBy($candidate, $worker)) {
                    return $this->stampClaim($candidate, $worker);
                }
            }

            return null;
        });

        if ($claimedJob === null) {
            return null;
        }

        // The fence is applied after the claim commits, so its HTTP calls never
        // run while the row lock is held. An issue a human already holds is
        // handed straight back rather than fenced.
        if ($claimedJob->kind === JobKind::Issue) {
            if ($this->fence->issueHeldByHuman($claimedJob->repo, $claimedJob->reference)) {
                $this->release($claimedJob);

                return null;
            }

            $this->fence->markClaimed($claimedJob->repo, $claimedJob->reference, $worker->worker_id);
        }

        // Broadcast only once the job is genuinely the worker's.
        JobClaimed::dispatch($claimedJob);

        return $claimedJob;
    }

    /**
     * Hand a just-claimed job back to the queue (a human holds its issue),
     * clearing the claim so another tick can reconsider it.
     *
     * @param  NightCrewJob  $job
     */
    private function release(NightCrewJob $job): void
    {
        DB::transaction(function () use ($job): void {
            $lockedJob = NightCrewJob::query()->lockForUpdate()->findOrFail($job->getKey());

            $lockedJob->status = JobStatus::Queued;
            $lockedJob->worker_id = null;
            $lockedJob->claimed_at = null;
            $lockedJob->claimed_by = null;
            $lockedJob->save();
        });
    }

    /**
     * The locked, ordered set of jobs that could plausibly be claimed: queued
     * jobs, plus contested issue jobs that another worker already holds.
     *
     * @param  Worker  $worker
     * @param  ?string  $stage
     *
     * @return Collection<int, NightCrewJob>
     */
    private function candidatesFor(Worker $worker, ?string $stage = null): Collection
    {
        return NightCrewJob::query()
            ->whereIn('repo', $worker->served_repos)
            ->where('next_due_at', '<=', now())
            ->when($stage === null, fn (Builder $query): Builder => $query->where('kind', '!=', JobKind::PullRequest))
            ->when($stage !== null, fn (Builder $query): Builder => $query->where('kind', JobKind::PullRequest)->where('payload->stage', $stage))
            ->where(function (Builder $query): void {
                $query->where('status', JobStatus::Queued)
                    ->orWhere(function (Builder $contestedQuery): void {
                        $contestedQuery->where('contested', true)
                            ->where('kind', JobKind::Issue)
                            ->where('status', JobStatus::Claimed);
                    });
            })
            ->orderByDesc('priority')
            ->orderBy('id')
            ->lockForUpdate()
            ->get();
    }

    /**
     * Decide whether the worker may claim this candidate.
     *
     * @param  NightCrewJob  $job
     * @param  Worker  $worker
     */
    private function isClaimableBy(NightCrewJob $job, Worker $worker): bool
    {
        if ($job->kind !== JobKind::PullRequest && NightCrewJob::query()
            ->where('repo', $job->repo)->where('kind', JobKind::PullRequest)
            ->whereIn('status', [JobStatus::Claimed, JobStatus::Running])->exists()) {
            return false;
        }
        if ($job->kind === JobKind::PullRequest && NightCrewJob::query()
            ->where('repo', $job->repo)->where('kind', '!=', JobKind::PullRequest)
            ->whereIn('status', [JobStatus::Claimed, JobStatus::Running])->exists()) {
            return false;
        }
        // A never-claimed job is free for the taking.
        if ($job->status === JobStatus::Queued) {
            return true;
        }

        // Otherwise only a contested issue job is still open, and only to a
        // worker that has not already claimed it.
        $alreadyClaimed = in_array($worker->worker_id, $job->claimers(), true);

        return $job->contested
            && $job->kind === JobKind::Issue
            && $job->status === JobStatus::Claimed
            && $alreadyClaimed === false;
    }

    /**
     * Stamp the claim onto the job and persist it.
     *
     * @param  NightCrewJob  $job
     * @param  Worker  $worker
     */
    private function stampClaim(NightCrewJob $job, Worker $worker): NightCrewJob
    {
        $claimers = $job->claimers();

        if (in_array($worker->worker_id, $claimers, true) === false) {
            $claimers[] = $worker->worker_id;
        }

        $job->status = JobStatus::Claimed;
        $job->worker_id = $worker->worker_id;
        $job->claimed_by = $claimers;
        $job->claimed_at = now();
        if ($job->kind === JobKind::PullRequest) {
            $job->claim_token = (string) Str::uuid();
        }
        $job->save();

        return $job;
    }
}
