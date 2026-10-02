<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Actions\Jobs\CreateJobAction;
use App\Http\Requests\StoreJobRequest;
use App\Http\Resources\JobResource;
use App\Services\Workers\WorkerResolver;
use Illuminate\Http\JsonResponse;

/**
 * The single authenticated door for creating jobs on the board.
 */
final class StoreJobController
{
    public function __construct(private CreateJobAction $createJob, private WorkerResolver $workerResolver) {}

    /**
     * Create a queued job for the repository named in the path.
     *
     * @param  string  $repo  The repository identifier from the route.
     * @param  StoreJobRequest  $request
     */
    public function __invoke(StoreJobRequest $request, string $repo): JsonResponse
    {
        if ($request->input('kind') === 'pull_request') {
            $worker = $this->workerResolver->resolve($request);
            abort_unless(in_array($repo, $worker->served_repos, true), 403);
            $request->validate(['reference' => ['required', 'regex:/^[1-9][0-9]*$/']]);
        }
        $job = $this->createJob->handle($repo, $request->validated());

        return JobResource::make($job)->response()->setStatusCode(201);
    }
}
