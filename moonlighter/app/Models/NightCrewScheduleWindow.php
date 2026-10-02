<?php

declare(strict_types=1);

namespace App\Models;

use App\Enums\OverrideMode;
use App\Enums\ScheduleWindowKind;
use Database\Factories\NightCrewScheduleWindowFactory;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Carbon;

/**
 * One weekly or override window that defines when the night crew may claim work.
 *
 * day_of_week: 0 = Sunday … 6 = Saturday (weekly rows only).
 * start_minute / end_minute: minutes from local midnight in [0, 1440); end is
 * exclusive. When end_minute <= start_minute the window wraps past midnight:
 * on the row's weekday [start_minute, 1440), and for weekly rows the early
 * half continues on the next weekday as [0, end_minute).
 *
 * @property ScheduleWindowKind $kind
 * @property string $timezone
 * @property int|null $day_of_week
 * @property int|null $start_minute
 * @property int|null $end_minute
 * @property Carbon|null $override_date
 * @property OverrideMode|null $override_mode
 * @property string|null $label
 * @property bool $enabled
 */
class NightCrewScheduleWindow extends Model
{
    /** @use HasFactory<NightCrewScheduleWindowFactory> */
    use HasFactory;

    /**
     * @var list<string>
     */
    protected $fillable = [
        'kind',
        'timezone',
        'day_of_week',
        'start_minute',
        'end_minute',
        'override_date',
        'override_mode',
        'label',
        'enabled',
    ];

    /**
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'kind' => ScheduleWindowKind::class,
            'day_of_week' => 'integer',
            'start_minute' => 'integer',
            'end_minute' => 'integer',
            'override_date' => 'date',
            'override_mode' => OverrideMode::class,
            'enabled' => 'boolean',
        ];
    }

    /**
     * @param  Builder<NightCrewScheduleWindow>  $query
     *
     * @return Builder<NightCrewScheduleWindow>
     */
    public function scopeEnabled(Builder $query): Builder
    {
        return $query->where('enabled', true);
    }

    /**
     * @param  Builder<NightCrewScheduleWindow>  $query
     *
     * @return Builder<NightCrewScheduleWindow>
     */
    public function scopeWeekly(Builder $query): Builder
    {
        return $query->where('kind', ScheduleWindowKind::Weekly);
    }

    /**
     * @param  Builder<NightCrewScheduleWindow>  $query
     *
     * @return Builder<NightCrewScheduleWindow>
     */
    public function scopeOverrides(Builder $query): Builder
    {
        return $query->where('kind', ScheduleWindowKind::Override);
    }

    /**
     * Whether the given minute-of-day falls inside this window (exclusive end).
     *
     * Overnight wrap: when end_minute <= start_minute, the range is
     * [start_minute, 1440) ∪ [0, end_minute) on the same date. Override rows use
     * this directly; weekly rows use containsMinuteOnOwnDay and
     * containsMinuteOnNextDay so a night shift is not also active on the early
     * morning of its own weekday.
     *
     * @param  int  $minuteOfDay  Local minute of the day.
     *
     * @return bool
     */
    public function containsMinute(int $minuteOfDay): bool
    {
        if ($this->start_minute === null || $this->end_minute === null) {
            return false;
        }

        $start = $this->start_minute;
        $end = $this->end_minute;

        if ($end <= $start) {
            return $minuteOfDay >= $start || $minuteOfDay < $end;
        }

        return $minuteOfDay >= $start && $minuteOfDay < $end;
    }

    /**
     * Whether a weekly row covers the minute on its own weekday.
     *
     * An overnight row covers only [start_minute, 1440) on its own weekday; its
     * early half belongs to the next weekday (see containsMinuteOnNextDay).
     *
     * @param  int  $minuteOfDay  Local minute of the day.
     *
     * @return bool
     */
    public function containsMinuteOnOwnDay(int $minuteOfDay): bool
    {
        if ($this->start_minute === null || $this->end_minute === null) {
            return false;
        }

        if ($this->end_minute <= $this->start_minute) {
            return $minuteOfDay >= $this->start_minute;
        }

        return $this->containsMinute($minuteOfDay);
    }

    /**
     * Whether a weekly row's overnight wrap carries the minute into the next weekday.
     *
     * Only overnight rows (end_minute <= start_minute) carry, covering
     * [0, end_minute) on the following weekday.
     *
     * @param  int  $minuteOfDay  Local minute of the day on the next weekday.
     *
     * @return bool
     */
    public function containsMinuteOnNextDay(int $minuteOfDay): bool
    {
        if ($this->start_minute === null || $this->end_minute === null) {
            return false;
        }

        if ($this->end_minute > $this->start_minute) {
            return false;
        }

        return $minuteOfDay < $this->end_minute;
    }
}
