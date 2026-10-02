<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Enums\JobKind;
use App\Http\Resources\JobResource;
use App\Models\NightCrewJob;
use App\Services\Workers\WorkerResolver;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/** Expose durable PR history and owned checkpoints to the local worker. */
final class ListPrJobsController
{
    public function __construct(private WorkerResolver $workerResolver) {}

    /**
     * Read a page of authorized PR jobs without revealing another worker's fence.
     *
     * @param  Request  $request
     */
    public function __invoke(Request $request): JsonResponse
    {
        $worker = $this->workerResolver->resolve($request);
        $jobs = NightCrewJob::query()->where('kind', JobKind::PullRequest)
            ->whereIn('repo', $worker->served_repos)->orderBy('id')->paginate(100);
        $jobs->getCollection()->transform(function (NightCrewJob $job) use ($worker, $request): array {
            $result = JobResource::make($job)->resolve($request);
            if ($job->worker_id !== $worker->worker_id) {
                unset($result['claim_token']);
            }

            return $result;
        });

        return response()->json($jobs);
    }
}
