<?php

declare(strict_types=1);

namespace App\Services;

use App\Enums\OverrideMode;
use App\Models\NightCrewScheduleWindow;
use Carbon\CarbonInterface;
use Illuminate\Support\Carbon;
use Illuminate\Support\Collection;

/**
 * Decide whether the night crew is inside an active claiming window.
 *
 * Fail-closed: with no enabled weekly rows, isActive is always false.
 * Time is always evaluated in self::TIMEZONE (America/Toronto). The per-row
 * timezone column is recorded but not read in v1. Overrides for the local
 * calendar date win over weekly rules. A block on the overnight shift's start
 * date cancels the whole shift, including next-morning carry (Friday block
 * suppresses Saturday 00:00-06:00 from Friday's 22:00-06:00). A Saturday
 * replace or block still governs that Saturday morning on its own (replace
 * drops the carry; block forces inactive for the whole local date).
 */
final class Schedule
{
    public const TIMEZONE = 'America/Toronto';

    /**
     * Whether claiming is allowed at $now (default: current UTC instant).
     *
     * @param  ?CarbonInterface  $now  Instant to evaluate; null means now.
     *
     * @return bool True when the night crew may claim work at that instant.
     */
    public function isActive(?CarbonInterface $now = null): bool
    {
        $instant = $now === null
            ? Carbon::now('UTC')
            : Carbon::instance($now)->utc();

        $local = $instant->copy()->timezone(self::TIMEZONE);
        $localDate = $local->toDateString();
        $minuteOfDay = ($local->hour * 60) + $local->minute;
        $dayOfWeek = $local->dayOfWeek; // 0 = Sunday … 6 = Saturday

        $overrides = NightCrewScheduleWindow::query()
            ->enabled()
            ->overrides()
            ->whereDate('override_date', $localDate)
            ->get();

        if ($overrides->isNotEmpty()) {
            return $this->evaluateOverrides($overrides, $minuteOfDay, $dayOfWeek, $localDate);
        }

        return $this->weeklyActive($dayOfWeek, $minuteOfDay, $localDate);
    }

    /**
     * Whether any enabled weekly window exists (used by the calendar fail-closed banner).
     *
     * @return bool
     */
    public function hasEnabledWeeklyWindows(): bool
    {
        return NightCrewScheduleWindow::query()->enabled()->weekly()->exists();
    }

    /**
     * Apply the local date's overrides: block beats replace beats extend.
     *
     * Today's block/replace/extend govern the local calendar date being
     * evaluated. Extend still ORs with weeklyActive, which may include
     * next-morning carry from yesterday's overnight weekly row — unless
     * yesterday itself has a block (that block cancels the whole overnight
     * shift, including this morning's wrap). Replace and non-block modes on
     * yesterday do not affect today's carry.
     *
     * @param  Collection<int, NightCrewScheduleWindow>  $overrides  Enabled overrides for the local date.
     * @param  int  $minuteOfDay  Local minute of the day.
     * @param  int  $dayOfWeek  Local weekday, 0 = Sunday.
     * @param  string  $localDate  Local Y-m-d being evaluated.
     *
     * @return bool
     */
    private function evaluateOverrides(Collection $overrides, int $minuteOfDay, int $dayOfWeek, string $localDate): bool
    {
        // block wins for the whole local date.
        if ($overrides->contains(fn (NightCrewScheduleWindow $window): bool => $window->override_mode === OverrideMode::Block)) {
            return false;
        }

        $replaces = $overrides->filter(
            fn (NightCrewScheduleWindow $window): bool => $window->override_mode === OverrideMode::Replace,
        );

        if ($replaces->isNotEmpty()) {
            return $replaces->contains(
                fn (NightCrewScheduleWindow $window): bool => $window->containsMinute($minuteOfDay),
            );
        }

        $extends = $overrides->filter(
            fn (NightCrewScheduleWindow $window): bool => $window->override_mode === OverrideMode::Extend,
        );

        if ($extends->isNotEmpty()) {
            if ($this->weeklyActive($dayOfWeek, $minuteOfDay, $localDate)) {
                return true;
            }

            return $extends->contains(
                fn (NightCrewScheduleWindow $window): bool => $window->containsMinute($minuteOfDay),
            );
        }

        // Enabled overrides present but none of the known modes — fail closed.
        return false;
    }

    /**
     * Whether an enabled weekly window covers this weekday and minute.
     *
     * Same-day rows cover only their own-day portion: an overnight row covers
     * [start_minute, 1440) on its weekday. Overnight rows on the previous
     * weekday cover [0, end_minute) on this morning, so a Friday 22:00-06:00
     * window is active Friday from 22:00 and Saturday before 06:00 only —
     * unless yesterday has an enabled block override, which cancels the whole
     * overnight shift including this morning carry.
     *
     * @param  int  $dayOfWeek  Local weekday, 0 = Sunday.
     * @param  int  $minuteOfDay  Local minute of the day.
     * @param  string  $localDate  Local Y-m-d being evaluated.
     *
     * @return bool
     */
    private function weeklyActive(int $dayOfWeek, int $minuteOfDay, string $localDate): bool
    {
        $previousDay = ($dayOfWeek + 6) % 7;

        // One fetch for both rules: this claim-path check runs on every isActive call.
        $weekly = NightCrewScheduleWindow::query()
            ->enabled()
            ->weekly()
            ->whereIn('day_of_week', [$dayOfWeek, $previousDay])
            ->get();

        if ($weekly->contains(
            fn (NightCrewScheduleWindow $window): bool => $window->day_of_week === $dayOfWeek
                && $window->containsMinuteOnOwnDay($minuteOfDay),
        )) {
            return true;
        }

        // Carry the early half of yesterday's overnight wrap into this morning.
        $carried = $weekly->contains(
            fn (NightCrewScheduleWindow $window): bool => $window->day_of_week === $previousDay
                && $window->containsMinuteOnNextDay($minuteOfDay),
        );

        if (! $carried) {
            return false;
        }

        // A block on the overnight shift's start date cancels next-morning carry.
        // Checked only once a carry row matches, so ordinary misses cost no extra query.
        return ! $this->dateHasBlock($this->previousLocalDate($localDate));
    }

    /**
     * Local calendar date immediately before $localDate in self::TIMEZONE.
     *
     * @param  string  $localDate  Local Y-m-d being evaluated.
     *
     * @return string Local Y-m-d of the previous calendar day.
     */
    private function previousLocalDate(string $localDate): string
    {
        return Carbon::parse($localDate, self::TIMEZONE)->subDay()->toDateString();
    }

    /**
     * Whether the given local date has an enabled block override.
     *
     * @param  string  $localDate  Local Y-m-d to check for a block override.
     *
     * @return bool True when an enabled block override exists for that date.
     */
    private function dateHasBlock(string $localDate): bool
    {
        return NightCrewScheduleWindow::query()
            ->enabled()
            ->overrides()
            ->whereDate('override_date', $localDate)
            ->where('override_mode', OverrideMode::Block)
            ->exists();
    }
}
