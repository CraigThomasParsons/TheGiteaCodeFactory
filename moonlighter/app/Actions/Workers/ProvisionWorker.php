<?php

declare(strict_types=1);

namespace App\Actions\Workers;

use App\Models\Worker;

/**
 * Register (or update) a worker and mint a Sanctum token for it.
 */
final class ProvisionWorker
{
    /**
     * Create or update the worker identified by $workerId with the given served
     * repositories, then issue a fresh API token it can use to claim jobs.
     *
     * @param  string  $workerId  Stable worker identity, e.g. the hostname.
     * @param  array<int, string>  $servedRepos  Repositories the worker can run.
     */
    public function handle(string $workerId, array $servedRepos): WorkerCredentials
    {
        // Re-registering an existing worker refreshes its served repos rather
        // than creating a duplicate identity.
        $worker = Worker::query()->updateOrCreate(
            ['worker_id' => $workerId],
            ['served_repos' => array_values($servedRepos)],
        );

        // The token name records which worker the token belongs to; the plain
        // text value is returned now because Sanctum never exposes it again.
        $newAccessToken = $worker->createToken($workerId);

        return new WorkerCredentials($worker, $newAccessToken->plainTextToken);
    }
}
