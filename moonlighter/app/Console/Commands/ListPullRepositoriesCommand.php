<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Services\Gitea\GiteaPullRequestGateway;
use Illuminate\Console\Command;

/**
 * Print the resolved repository list, one per line.
 *
 * The PR pipeline wrapper drives shell stages that cannot expand the '*'
 * wildcard themselves. Rather than teach each of them to discover repositories
 * — three more places to drift — they ask here, so the expansion happens once.
 */
final class ListPullRepositoriesCommand extends Command
{
    protected $signature = 'nightcrew:list-pr-repos';

    protected $description = 'Print the repositories the PR pipeline may touch, one per line';

    /**
     * Print each resolved repository on its own line.
     *
     * @param  GiteaPullRequestGateway  $gateway
     *
     * @return int
     */
    public function handle(GiteaPullRequestGateway $gateway): int
    {
        foreach ($gateway->pipelineRepositories() as $repository) {
            $this->line($repository);
        }

        return self::SUCCESS;
    }
}
