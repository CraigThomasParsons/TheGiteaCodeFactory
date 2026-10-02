<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Actions\Jobs\TransitionJobStatus;
use App\Enums\JobStatus;
use App\Http\Requests\UpdateJobStatusRequest;
use App\Http\Resources\JobResource;
use App\Models\NightCrewJob;
use App\Services\Workers\WorkerResolver;
use Illuminate\Http\JsonResponse;

/**
 * Record a worker's reported status change for a job.
 */
final class UpdateJobStatusController
{
    public function __construct(
        private WorkerResolver $workerResolver,
        private TransitionJobStatus $transitionJobStatus,
    ) {}

    /**
     * Transition the job to the reported status on behalf of the worker.
     *
     * @param  NightCrewJob  $job  Route-bound by id.
     * @param  UpdateJobStatusRequest  $request
     */
    public function __invoke(UpdateJobStatusRequest $request, NightCrewJob $job): JsonResponse
    {
        $worker = $this->workerResolver->resolve($request);
        $target = JobStatus::from($request->validated('status'));

        $updatedJob = $this->transitionJobStatus->handle($job, $worker, $target,
            $request->input('receipt', []), $request->input('claim_token'));

        return JobResource::make($updatedJob)->response();
    }
}
