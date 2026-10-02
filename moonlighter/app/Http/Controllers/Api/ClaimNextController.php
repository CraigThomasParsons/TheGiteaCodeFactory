<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Actions\Jobs\ClaimNextJob;
use App\Http\Resources\JobResource;
use App\Services\Workers\WorkerResolver;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Hand the calling worker its next job, or 204 when there is nothing to do.
 */
final class ClaimNextController
{
    public function __construct(
        private WorkerResolver $workerResolver,
        private ClaimNextJob $claimNextJob,
    ) {}

    /**
     * Claim the next actionable job for the authenticated worker.
     *
     * @param  Request  $request
     */
    public function __invoke(Request $request): JsonResponse|Response
    {
        $worker = $this->workerResolver->resolve($request);
        $validated = $request->validate([
            'stage' => ['sometimes', 'in:review,resolve,arbitrate,post_merge'],
            'recover_stale' => ['sometimes', 'boolean'],
        ]);
        $job = $this->claimNextJob->forWorker($worker, data_get($validated, 'stage'),
            (bool) data_get($validated, 'recover_stale', false));

        // No actionable work is a normal, quiet outcome, not an error.
        if ($job === null) {
            return response()->noContent();
        }

        return JobResource::make($job)->response();
    }
}
