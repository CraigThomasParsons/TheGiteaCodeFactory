<?php

declare(strict_types=1);

namespace App\Enums;

/**
 * How an override-date window interacts with the weekly schedule.
 *
 * - block: force inactive for the whole local date
 * - replace: ignore weekly; active only inside replace windows
 * - extend: active if weekly OR inside extend windows
 */
enum OverrideMode: string
{
    case Block = 'block';
    case Replace = 'replace';
    case Extend = 'extend';
}
