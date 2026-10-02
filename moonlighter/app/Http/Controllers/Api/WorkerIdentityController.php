<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Services\Workers\WorkerResolver;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * Report the identity and served repositories of the calling worker.
 *
 * This is the smallest authenticated endpoint that exercises the whole token
 * chain, and it doubles as a health/identity probe for a worker's client.
 */
final class WorkerIdentityController
{
    public function __construct(private WorkerResolver $workerResolver) {}

    /**
     * Return the authenticated worker's identity and served repositories.
     *
     * @param  Request  $request
     */
    public function __invoke(Request $request): JsonResponse
    {
        $worker = $this->workerResolver->resolve($request);

        return response()->json([
            'worker_id' => $worker->worker_id,
            'served_repos' => $worker->served_repos,
        ]);
    }
}
