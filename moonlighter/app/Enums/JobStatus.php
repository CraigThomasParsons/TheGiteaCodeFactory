<?php

declare(strict_types=1);

namespace App\Enums;

/**
 * The lifecycle status of a NightCrewJob.
 *
 * A job starts Queued, is atomically moved to Claimed by a worker, then Running
 * while it executes, and finally Done or Failed. Maintenance jobs return to
 * Queued after Done so they can recur; issue jobs are terminal on Done.
 */
enum JobStatus: string
{
    case Queued = 'queued';
    case Claimed = 'claimed';
    case Running = 'running';
    case Done = 'done';
    case Failed = 'failed';
}
