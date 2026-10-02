<?php

declare(strict_types=1);

namespace App\Actions\Schedule;

use App\Enums\ScheduleWindowKind;
use App\Models\NightCrewScheduleWindow;
use Illuminate\Validation\ValidationException;

/**
 * Shared checks for the schedule upsert actions, so the [0, 1440) minute rule
 * and the "never change a row's kind" rule live in one place.
 */
final class ScheduleWindowGuard
{
    /**
     * Reject a minute-of-day outside [0, 1440).
     *
     * @param  int  $minute  Minutes from local midnight.
     * @param  string  $field  Validation key the error is reported under.
     *
     * @return void
     *
     * @throws ValidationException
     */
    public function assertMinute(int $minute, string $field): void
    {
        if ($minute < 0 || $minute >= 1440) {
            throw ValidationException::withMessages([
                $field => "{$field} must be in [0, 1440).",
            ]);
        }
    }

    /**
     * Load the row being updated, or start a new one, refusing to change an
     * existing row into a different kind.
     *
     * @param  int|null  $id  Existing row id, or null to create.
     * @param  ScheduleWindowKind  $kind  The kind the caller is upserting.
     * @param  string  $wrongKindMessage  Error reported under `id` on a kind mismatch.
     *
     * @return NightCrewScheduleWindow
     *
     * @throws ValidationException
     */
    public function findOrNewOfKind(?int $id, ScheduleWindowKind $kind, string $wrongKindMessage): NightCrewScheduleWindow
    {
        if ($id === null) {
            return new NightCrewScheduleWindow;
        }

        $window = NightCrewScheduleWindow::query()->findOrFail($id);

        if ($window->kind !== $kind) {
            throw ValidationException::withMessages([
                'id' => $wrongKindMessage,
            ]);
        }

        return $window;
    }
}
