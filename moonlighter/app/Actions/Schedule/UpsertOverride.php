<?php

declare(strict_types=1);

namespace App\Actions\Schedule;

use App\Enums\OverrideMode;
use App\Enums\ScheduleWindowKind;
use App\Models\NightCrewScheduleWindow;
use App\Services\Schedule;
use Illuminate\Support\Arr;
use Illuminate\Validation\ValidationException;

/**
 * Create or update a one-day override (block / replace / extend).
 */
final class UpsertOverride
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
     *     override_date: string,
     *     override_mode: string,
     *     start_minute?: int|null,
     *     end_minute?: int|null,
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
        $mode = OverrideMode::from($data['override_mode']);
        $start = Arr::get($data, 'start_minute');
        $end = Arr::get($data, 'end_minute');

        if ($mode === OverrideMode::Block) {
            $start = null;
            $end = null;
        } else {
            if ($start === null || $end === null) {
                throw ValidationException::withMessages([
                    'start_minute' => 'replace/extend overrides require start_minute and end_minute.',
                ]);
            }

            $start = (int) $start;
            $end = (int) $end;
            $this->guard->assertMinute($start, 'start_minute');
            $this->guard->assertMinute($end, 'end_minute');
        }

        $id = Arr::get($data, 'id');
        $window = $this->guard->findOrNewOfKind(
            $id ? (int) $id : null,
            ScheduleWindowKind::Override,
            'Cannot upsert a non-override window as override.',
        );

        $window->kind = ScheduleWindowKind::Override;
        $window->timezone = Schedule::TIMEZONE;
        $window->day_of_week = null;
        $window->override_date = $data['override_date'];
        $window->override_mode = $mode;
        $window->start_minute = $start;
        $window->end_minute = $end;
        $window->label = Arr::get($data, 'label');
        $window->enabled = (bool) Arr::get($data, 'enabled', true);
        $window->save();

        return $window;
    }
}
