<?php

declare(strict_types=1);

namespace App\Enums;

/**
 * Whether a schedule window is a recurring weekday rule or a one-day override.
 */
enum ScheduleWindowKind: string
{
    case Weekly = 'weekly';
    case Override = 'override';
}
