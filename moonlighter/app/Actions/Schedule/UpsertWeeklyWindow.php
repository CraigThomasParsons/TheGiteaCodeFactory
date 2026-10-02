<?php

declare(strict_types=1);

namespace App\Actions\Schedule;

use App\Enums\ScheduleWindowKind;
use App\Models\NightCrewScheduleWindow;
use App\Services\Schedule;
use Illuminate\Support\Arr;
use Illuminate\Validation\ValidationException;

/**
 * Create or update an enabled weekly schedule window.
 *
 * day_of_week: 0 = Sunday … 6 = Saturday.
 * Minutes are from local midnight in [0, 1440); end is exclusive.
 */
final class UpsertWeeklyWindow
{
    /**
     * Inject the shared window checks.
     *
     * @param  ScheduleWindowGuard  $guard  Shared minute and kind checks.
     */
    public function __construct(private readonly ScheduleWindowGuard $guard) {}

    /**
     * @param  array{
     *     id?: int|null,
     *     day_of_week: int,
     *     start_minute: int,
     *     end_minute: int,
     *     label?: string|null,
     *     enabled?: bool,
     * }  $data
     *
     * @return NightCrewScheduleWindow The saved row.
     *
     * @throws ValidationException
     */
    public function handle(array $data): NightCrewScheduleWindow
    {
        $dayOfWeek = (int) $data['day_of_week'];
        $start = (int) $data['start_minute'];
        $end = (int) $data['end_minute'];

        $this->assertDayOfWeek($dayOfWeek);
        $this->guard->assertMinute($start, 'start_minute');
        $this->guard->assertMinute($end, 'end_minute');

        $id = Arr::get($data, 'id');
        $window = $this->guard->findOrNewOfKind(
            $id ? (int) $id : null,
            ScheduleWindowKind::Weekly,
            'Cannot upsert a non-weekly window as weekly.',
        );

        $window->kind = ScheduleWindowKind::Weekly;
        $window->timezone = Schedule::TIMEZONE;
        $window->day_of_week = $dayOfWeek;
        $window->start_minute = $start;
        $window->end_minute = $end;
        $window->override_date = null;
        $window->override_mode = null;
        $window->label = Arr::get($data, 'label');
        $window->enabled = (bool) Arr::get($data, 'enabled', true);
        $window->save();

        return $window;
    }

    /**
     * Reject a weekday outside 0 (Sunday) through 6 (Saturday).
     *
     * @param  int  $day  Weekday number.
     *
     * @return void
     *
     * @throws ValidationException
     */
    private function assertDayOfWeek(int $day): void
    {
        if ($day < 0 || $day > 6) {
            throw ValidationException::withMessages([
                'day_of_week' => 'day_of_week must be 0 (Sunday) through 6 (Saturday).',
            ]);
        }
    }
}
