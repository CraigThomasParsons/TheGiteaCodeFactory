<?php

declare(strict_types=1);

namespace App\Livewire;

use App\Actions\Schedule\DeleteWindow;
use App\Actions\Schedule\UpsertOverride;
use App\Actions\Schedule\UpsertWeeklyWindow;
use App\Enums\OverrideMode;
use App\Models\NightCrewScheduleWindow;
use App\Services\Schedule;
use Illuminate\Contracts\View\View;
use Illuminate\Support\Carbon;
use Illuminate\Validation\Rule;
use Livewire\Attributes\Title;
use Livewire\Component;

/**
 * Edit weekly active hours and one-day overrides for the night crew schedule.
 *
 * Week strip starts Monday. Timezone is fixed to America/Toronto.
 */
#[Title('Schedule — Night Crew')]
class ScheduleCalendar extends Component
{
    public string $timezone = Schedule::TIMEZONE;

    /** @var array<int, string> */
    public array $dayLabels = [
        1 => 'Mon',
        2 => 'Tue',
        3 => 'Wed',
        4 => 'Thu',
        5 => 'Fri',
        6 => 'Sat',
        0 => 'Sun',
    ];

    // Weekly form
    public ?int $weeklyId = null;

    public int $weeklyDayOfWeek = 1;

    public string $weeklyStart = '06:00';

    public string $weeklyEnd = '12:00';

    public string $weeklyLabel = '';

    public bool $weeklyEnabled = true;

    // Override form
    public ?int $overrideId = null;

    public string $overrideDate = '';

    public string $overrideMode = 'block';

    public string $overrideStart = '06:00';

    public string $overrideEnd = '12:00';

    public string $overrideLabel = '';

    public bool $overrideEnabled = true;

    /**
     * Default the override date to today in the schedule timezone.
     *
     * @return void
     */
    public function mount(): void
    {
        $this->overrideDate = Carbon::now(Schedule::TIMEZONE)->toDateString();
    }

    /**
     * Load a weekly window into the weekly form.
     *
     * @param  int  $id  Weekly window id.
     *
     * @return void
     */
    public function editWeekly(int $id): void
    {
        $window = NightCrewScheduleWindow::query()->findOrFail($id);
        $this->weeklyId = $window->id;
        $this->weeklyDayOfWeek = (int) $window->day_of_week;
        $this->weeklyStart = $this->minuteToTime((int) $window->start_minute);
        $this->weeklyEnd = $this->minuteToTime((int) $window->end_minute);
        $this->weeklyLabel = (string) $window->label;
        $this->weeklyEnabled = $window->enabled;
    }

    /**
     * Clear the weekly form back to its defaults.
     *
     * @return void
     */
    public function resetWeeklyForm(): void
    {
        $this->weeklyId = null;
        $this->weeklyDayOfWeek = 1;
        $this->weeklyStart = '06:00';
        $this->weeklyEnd = '12:00';
        $this->weeklyLabel = '';
        $this->weeklyEnabled = true;
        $this->resetValidation();
    }

    /**
     * Validate the weekly form and create or update the window.
     *
     * @param  UpsertWeeklyWindow  $upsert  Action that persists the window.
     *
     * @return void
     */
    public function saveWeekly(UpsertWeeklyWindow $upsert): void
    {
        $validated = $this->validate([
            'weeklyDayOfWeek' => ['required', 'integer', 'min:0', 'max:6'],
            // date_format:H:i rejects out-of-range times like 25:99 here, on the
            // form field, instead of in the action under a key the form never shows.
            'weeklyStart' => ['required', 'date_format:H:i'],
            'weeklyEnd' => ['required', 'date_format:H:i'],
            'weeklyLabel' => ['nullable', 'string', 'max:255'],
            'weeklyEnabled' => ['boolean'],
        ]);

        $upsert->handle([
            'id' => $this->weeklyId,
            'day_of_week' => (int) $validated['weeklyDayOfWeek'],
            'start_minute' => $this->timeToMinute($validated['weeklyStart']),
            'end_minute' => $this->timeToMinute($validated['weeklyEnd']),
            'label' => $validated['weeklyLabel'] !== '' ? $validated['weeklyLabel'] : null,
            'enabled' => $validated['weeklyEnabled'],
        ]);

        $this->resetWeeklyForm();
    }

    /**
     * Load an override into the override form.
     *
     * @param  int  $id  Override window id.
     *
     * @return void
     */
    public function editOverride(int $id): void
    {
        $window = NightCrewScheduleWindow::query()->findOrFail($id);
        $this->overrideId = $window->id;
        $this->overrideDate = $window->override_date === null
            ? Carbon::now(Schedule::TIMEZONE)->toDateString()
            : $window->override_date->toDateString();
        $this->overrideMode = $window->override_mode === null
            ? OverrideMode::Block->value
            : $window->override_mode->value;
        $this->overrideStart = $window->start_minute !== null
            ? $this->minuteToTime((int) $window->start_minute)
            : '06:00';
        $this->overrideEnd = $window->end_minute !== null
            ? $this->minuteToTime((int) $window->end_minute)
            : '12:00';
        $this->overrideLabel = (string) $window->label;
        $this->overrideEnabled = $window->enabled;
    }

    /**
     * Clear the override form back to its defaults.
     *
     * @return void
     */
    public function resetOverrideForm(): void
    {
        $this->overrideId = null;
        $this->overrideDate = Carbon::now(Schedule::TIMEZONE)->toDateString();
        $this->overrideMode = OverrideMode::Block->value;
        $this->overrideStart = '06:00';
        $this->overrideEnd = '12:00';
        $this->overrideLabel = '';
        $this->overrideEnabled = true;
        $this->resetValidation();
    }

    /**
     * Validate the override form and create or update the override.
     *
     * @param  UpsertOverride  $upsert  Action that persists the override.
     *
     * @return void
     */
    public function saveOverride(UpsertOverride $upsert): void
    {
        $validated = $this->validate([
            'overrideDate' => ['required', 'date'],
            'overrideMode' => ['required', Rule::enum(OverrideMode::class)],
            // replace/extend need both times; block ignores them.
            'overrideStart' => ['exclude_if:overrideMode,block', 'required', 'date_format:H:i'],
            'overrideEnd' => ['exclude_if:overrideMode,block', 'required', 'date_format:H:i'],
            'overrideLabel' => ['nullable', 'string', 'max:255'],
            'overrideEnabled' => ['boolean'],
        ]);

        $mode = OverrideMode::from($validated['overrideMode']);

        // Block overrides carry no times; replace/extend read the form's bound values.
        $startMinute = null;
        $endMinute = null;

        if ($mode !== OverrideMode::Block) {
            $startMinute = $this->timeToMinute($this->overrideStart);
            $endMinute = $this->timeToMinute($this->overrideEnd);
        }

        $upsert->handle([
            'id' => $this->overrideId,
            'override_date' => $validated['overrideDate'],
            'override_mode' => $mode->value,
            'start_minute' => $startMinute,
            'end_minute' => $endMinute,
            'label' => $validated['overrideLabel'] !== '' ? $validated['overrideLabel'] : null,
            'enabled' => $validated['overrideEnabled'],
        ]);

        $this->resetOverrideForm();
    }

    /**
     * Delete a window and clear whichever form was editing it.
     *
     * @param  int  $id  Window id.
     * @param  DeleteWindow  $delete  Action that removes the window.
     *
     * @return void
     */
    public function deleteWindow(int $id, DeleteWindow $delete): void
    {
        $window = NightCrewScheduleWindow::query()->findOrFail($id);
        $delete->handle($window);

        if ($this->weeklyId === $id) {
            $this->resetWeeklyForm();
        }

        if ($this->overrideId === $id) {
            $this->resetOverrideForm();
        }
    }

    /**
     * Render the Monday-first week strip, overrides, and current status.
     *
     * @param  Schedule  $schedule  Evaluates the active and fail-closed state.
     *
     * @return View
     */
    public function render(Schedule $schedule): View
    {
        // Grouped by weekday; the Monday-first order comes from $weekDays below,
        // so no SQL-side day ordering is needed.
        $weekly = NightCrewScheduleWindow::query()
            ->weekly()
            ->orderBy('start_minute')
            ->get()
            ->groupBy(fn (NightCrewScheduleWindow $window) => (int) $window->day_of_week);

        $overrides = NightCrewScheduleWindow::query()
            ->overrides()
            ->orderByDesc('override_date')
            ->orderBy('id')
            ->get();

        // Monday-first strip for the current local week.
        $weekStart = Carbon::now(Schedule::TIMEZONE)->startOfWeek(Carbon::MONDAY);
        $weekDays = collect(range(0, 6))->map(function (int $offset) use ($weekStart, $weekly) {
            $date = $weekStart->copy()->addDays($offset);
            $dow = $date->dayOfWeek;

            return [
                'date' => $date->toDateString(),
                'label' => $this->dayLabels[$dow],
                'day_of_week' => $dow,
                'windows' => $weekly->get($dow, collect()),
            ];
        });

        return view('livewire.schedule-calendar', [
            'weekDays' => $weekDays,
            'overrides' => $overrides,
            'failClosed' => ! $schedule->hasEnabledWeeklyWindows(),
            'isActiveNow' => $schedule->isActive(),
        ]);
    }

    /**
     * Convert an H:i string to minutes from midnight.
     *
     * @param  string  $hhmm  Time as H:i.
     *
     * @return int
     */
    private function timeToMinute(string $hhmm): int
    {
        [$hours, $minutes] = array_map('intval', explode(':', $hhmm));

        return ($hours * 60) + $minutes;
    }

    /**
     * Convert minutes from midnight to an H:i string, clamped to the day.
     *
     * @param  int  $minute  Minutes from midnight.
     *
     * @return string
     */
    private function minuteToTime(int $minute): string
    {
        $minute = max(0, min(1439, $minute));

        return sprintf('%02d:%02d', intdiv($minute, 60), $minute % 60);
    }
}
