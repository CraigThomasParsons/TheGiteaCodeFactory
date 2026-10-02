<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Actions\Pulls\LabelPullRequests;
use Illuminate\Console\Command;
use Illuminate\Support\Arr;

final class LabelPullRequestsCommand extends Command
{
    protected $signature = 'nightcrew:label-prs {--dry-run : Report what would change without touching Gitea}';

    protected $description = 'Apply review labels to open pull requests so the label-driven ticks can see them';

    /**
     * Run the sweep and print one line per repository and per label change.
     *
     * @param  LabelPullRequests  $action
     *
     * @return int
     */
    public function handle(LabelPullRequests $action): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $result = $action->handle($dryRun);

        foreach ($result['repositories'] as $repository => $detail) {
            if (Arr::get($detail, 'available', false) === false) {
                $this->warn(sprintf('  %-42s UNAVAILABLE: %s', $repository, Arr::get($detail, 'error', 'unknown')));

                continue;
            }

            $this->line(sprintf('  %-42s %d open', $repository, $detail['open']));

            foreach ($detail['actions'] as $change) {
                $this->line(sprintf(
                    '      #%-5s %-9s +%-20s %s',
                    $change['pr'],
                    $change['kind'],
                    implode(',', $change['add']),
                    $change['why'],
                ));
            }
        }

        $this->newLine();
        $this->info(sprintf(
            '%slabelled=%d refreshed=%d granted=%d skipped=%d',
            $dryRun ? 'DRY RUN — ' : '',
            $result['labelled'],
            $result['refreshed'],
            $result['granted'],
            $result['skipped'],
        ));

        return self::SUCCESS;
    }
}
