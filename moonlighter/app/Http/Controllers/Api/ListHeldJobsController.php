<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Enums\JobStatus;
use App\Http\Resources\HeldJobResource;
use App\Models\NightCrewJob;
use App\Services\Workers\WorkerResolver;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\AnonymousResourceCollection;

/**
 * List the claimed or running jobs the calling worker currently holds.
 *
 * Read-only: a local bridge uses it after a restart or a lost claim response to
 * reconcile its ledger against the coordinator, which stays the sole authority
 * on who holds what. It never claims, releases or transitions anything.
 */
final class ListHeldJobsController
{
    public function __construct(private WorkerResolver $workerResolver) {}

    /**
     * Return the authenticated worker's own active claims, oldest first.
     *
     * @param  Request  $request
     */
    public function __invoke(Request $request): AnonymousResourceCollection
    {
        $worker = $this->workerResolver->resolve($request);

        // Only worker_id is trusted as ownership: another worker's claim (or a
        // contested race it later joined) is never exposed with its fence.
        $jobs = NightCrewJob::query()
            ->where('worker_id', $worker->worker_id)
            ->whereIn('status', [JobStatus::Claimed, JobStatus::Running])
            ->orderBy('id')
            ->get();

        return HeldJobResource::collection($jobs);
    }
}
