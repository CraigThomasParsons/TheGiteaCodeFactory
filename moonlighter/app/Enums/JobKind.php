<?php

declare(strict_types=1);

namespace App\Enums;

/**
 * The kind of a NightCrewJob.
 *
 * An Issue job is one-time and references a tracker issue; a Maintenance job is
 * recurring, has no tracker ticket, and becomes workable again when it is due.
 */
enum JobKind: string
{
    case Issue = 'issue';
    case Maintenance = 'maintenance';
    case PullRequest = 'pull_request';
}
