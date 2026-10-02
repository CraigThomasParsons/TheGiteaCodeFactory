<?php

declare(strict_types=1);

namespace App\Actions\Jobs;

use App\Services\Gitea\GiteaReadyIssueGateway;
use Throwable;

/**
 * Scan configured repositories independently and admit their ready issues.
 */
final class IntakeReadyGiteaIssues
{
    public function __construct(
        private GiteaReadyIssueGateway $gateway,
        private CreateReadyIssueJob $createJob,
    ) {}

    /**
     * Run one bounded scan and return transparent repository-level evidence.
     *
     * @return array{created: int, existing: int, repositories: array<string, array<string, mixed>>}
     */
    public function handle(): array
    {
        $result = ['created' => 0, 'existing' => 0, 'repositories' => []];

        foreach ($this->repositories() as $repository) {
            try {
                $issues = $this->gateway->fetch($repository);
                $result['repositories'][$repository] = ['available' => true, 'eligible' => count($issues)];

                foreach ($issues as $issue) {
                    $job = $this->createJob->handle($issue);
                    $bucket = $job->wasRecentlyCreated ? 'created' : 'existing';
                    $result[$bucket]++;
                }
            } catch (Throwable $exception) {
                // One tracker failure must not hide ready work from healthy
                // repositories; the response preserves explicit failure evidence.
                $result['repositories'][$repository] = [
                    'available' => false,
                    'eligible' => 0,
                    'error' => $exception->getMessage(),
                ];
            }
        }

        return $result;
    }

    /**
     * Return the canonical, explicitly configured repository inventory.
     *
     * @return list<string>
     */
    private function repositories(): array
    {
        /** @var list<string> $repositories */
        $repositories = config('nightcrew.ready_intake.repositories');

        return $repositories;
    }
}
