<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Services\Schedule;
use Illuminate\Console\Command;

/**
 * Answer "may the crew work right now?" with an exit code.
 *
 * The schedule windows are the single source of truth for when unattended work
 * happens. Anything outside this application — the PR pipeline wrapper, a cron
 * line, a future runner — must ask here rather than encode its own hours. Two
 * sources of truth for that question is exactly how the night-crew client spent
 * weeks starting on time and claiming nothing.
 */
final class ScheduleActiveCommand extends Command
{
    protected $signature = 'nightcrew:schedule-active {--quiet-output : Print nothing; use the exit code only}';

    protected $description = 'Exit 0 when inside a crew schedule window, 1 when outside';

    /**
     * Print and return whether a schedule window is open right now.
     *
     * @param  Schedule  $schedule
     *
     * @return int 0 inside a window, 1 outside.
     */
    public function handle(Schedule $schedule): int
    {
        $active = $schedule->isActive();

        if (! $this->option('quiet-output')) {
            $this->line($active ? 'active' : 'outside-window');
        }

        return $active ? self::SUCCESS : self::FAILURE;
    }
}
