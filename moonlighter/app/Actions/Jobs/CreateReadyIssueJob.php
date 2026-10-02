<?php

declare(strict_types=1);

namespace App\Actions\Jobs;

use App\Enums\JobKind;
use App\Enums\JobStatus;
use App\Events\JobCreated;
use App\Models\NightCrewJob;
use App\ValueObjects\ReadyGiteaIssue;

/**
 * Idempotently admit one externally discovered Gitea issue through Intake.
 */
final class CreateReadyIssueJob
{
    /**
     * Create the issue job once, returning the existing job on later scans.
     *
     * @param  ReadyGiteaIssue  $issue
     */
    public function handle(ReadyGiteaIssue $issue): NightCrewJob
    {
        $job = NightCrewJob::query()->firstOrCreate(
            ['source_key' => $issue->sourceKey()],
            [
                'repo' => $issue->repository,
                'kind' => JobKind::Issue,
                'reference' => $issue->reference(),
                'payload' => [
                    'title' => $issue->title,
                    'url' => $issue->url,
                    'source' => 'gitea-ready-intake',
                ],
                'priority' => 0,
                'contested' => false,
                'status' => JobStatus::Queued,
                'next_due_at' => now(),
            ],
        );

        // Existing jobs retain their lifecycle state. Only a newly admitted
        // ticket announces itself to the live coordinator board.
        if ($job->wasRecentlyCreated) {
            JobCreated::dispatch($job);
        }

        return $job;
    }
}
