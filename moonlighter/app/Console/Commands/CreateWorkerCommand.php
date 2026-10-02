<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Actions\Workers\ProvisionWorker;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;

#[Signature('night-crew:worker:create {worker_id : Stable worker identity, e.g. the hostname} {--repos= : Comma-separated repositories this worker serves}')]
#[Description('Register a worker and mint a Sanctum API token it uses to claim jobs.')]
class CreateWorkerCommand extends Command
{
    /**
     * Register the worker and print its one-time token.
     *
     * @param  ProvisionWorker  $provisionWorker
     */
    public function handle(ProvisionWorker $provisionWorker): int
    {
        $workerId = trim((string) $this->argument('worker_id'));

        // Guard: a worker is meaningless without a stable identity to stamp claims.
        if ($workerId === '') {
            $this->error('A worker_id is required.');

            return self::FAILURE;
        }

        $servedRepos = $this->parseRepos((string) $this->option('repos'));

        // Guard: a worker that serves no repos could never be handed any job.
        if ($servedRepos === []) {
            $this->error('At least one repository is required via --repos.');

            return self::FAILURE;
        }

        $credentials = $provisionWorker->handle($workerId, $servedRepos);

        $this->info("Worker [{$workerId}] registered for: ".implode(', ', $servedRepos));
        $this->line('API token (shown once — store it securely):');
        $this->line($credentials->plainTextToken);

        return self::SUCCESS;
    }

    /**
     * Split a comma-separated repos option into a clean list of identifiers.
     *
     * @param  string  $rawRepos
     *
     * @return array<int, string>
     */
    private function parseRepos(string $rawRepos): array
    {
        $candidates = explode(',', $rawRepos);
        $trimmed = array_map(static fn (string $repo): string => trim($repo), $candidates);

        return array_values(array_filter($trimmed, static fn (string $repo): bool => $repo !== ''));
    }
}
