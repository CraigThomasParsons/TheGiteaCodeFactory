<?php

declare(strict_types=1);

namespace App\Actions\Schedule;

use App\Models\NightCrewScheduleWindow;

/**
 * Permanently remove a schedule window (weekly or override).
 */
final class DeleteWindow
{
    /**
     * Delete the given window.
     *
     * @param  NightCrewScheduleWindow  $window  The weekly or override row to remove.
     *
     * @return void
     */
    public function handle(NightCrewScheduleWindow $window): void
    {
        $window->delete();
    }
}
