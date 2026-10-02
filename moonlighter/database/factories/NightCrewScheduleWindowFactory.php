<?php

declare(strict_types=1);

namespace Database\Factories;

use App\Enums\OverrideMode;
use App\Enums\ScheduleWindowKind;
use App\Models\NightCrewScheduleWindow;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<NightCrewScheduleWindow>
 */
class NightCrewScheduleWindowFactory extends Factory
{
    /**
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'kind' => ScheduleWindowKind::Weekly,
            'timezone' => 'America/Toronto',
            'day_of_week' => 1,
            'start_minute' => 360,
            'end_minute' => 720,
            'override_date' => null,
            'override_mode' => null,
            'label' => null,
            'enabled' => true,
        ];
    }

    /**
     * An enabled weekly window for a specific weekday.
     *
     * @param  int  $dayOfWeek
     * @param  int  $startMinute
     * @param  int  $endMinute
     */
    public function weekly(int $dayOfWeek, int $startMinute = 360, int $endMinute = 720): static
    {
        return $this->state(fn (): array => [
            'kind' => ScheduleWindowKind::Weekly,
            'day_of_week' => $dayOfWeek,
            'start_minute' => $startMinute,
            'end_minute' => $endMinute,
            'override_date' => null,
            'override_mode' => null,
        ]);
    }

    /**
     * An enabled override for a specific local date.
     *
     * @param  string  $date
     * @param  OverrideMode  $mode
     * @param  int  $startMinute
     * @param  int  $endMinute
     */
    public function override(string $date, OverrideMode $mode, int $startMinute = 360, int $endMinute = 720): static
    {
        return $this->state(fn (): array => [
            'kind' => ScheduleWindowKind::Override,
            'day_of_week' => null,
            'override_date' => $date,
            'override_mode' => $mode,
            'start_minute' => $mode === OverrideMode::Block ? null : $startMinute,
            'end_minute' => $mode === OverrideMode::Block ? null : $endMinute,
        ]);
    }

    /**
     * Mark the window disabled.
     *
     * @return static
     */
    public function disabled(): static
    {
        return $this->state(fn (): array => [
            'enabled' => false,
        ]);
    }
}
