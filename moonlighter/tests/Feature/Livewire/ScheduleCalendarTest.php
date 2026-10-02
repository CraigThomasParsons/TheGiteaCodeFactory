<?php

declare(strict_types=1);

namespace Tests\Feature\Livewire;

use App\Enums\OverrideMode;
use App\Enums\ScheduleWindowKind;
use App\Livewire\ScheduleCalendar;
use App\Models\NightCrewScheduleWindow;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class ScheduleCalendarTest extends TestCase
{
    use RefreshDatabase;

    public function test_schedule_route_renders(): void
    {
        $this->get('/schedule')->assertOk()->assertSee('Schedule');
    }

    public function test_renders_seeded_weekly_windows_and_timezone_chip(): void
    {
        Livewire::test(ScheduleCalendar::class)
            ->assertOk()
            ->assertSee('America/Toronto')
            ->assertSee('Mon')
            ->assertSee('06:00');
    }

    public function test_can_upsert_a_weekly_window(): void
    {
        Livewire::test(ScheduleCalendar::class)
            ->set('weeklyDayOfWeek', 6)
            ->set('weeklyStart', '08:00')
            ->set('weeklyEnd', '10:00')
            ->set('weeklyLabel', 'Saturday morning')
            ->call('saveWeekly')
            ->assertHasNoErrors();

        $this->assertDatabaseHas('night_crew_schedule_windows', [
            'kind' => ScheduleWindowKind::Weekly->value,
            'day_of_week' => 6,
            'start_minute' => 480,
            'end_minute' => 600,
            'label' => 'Saturday morning',
            'enabled' => 1,
        ]);
    }

    public function test_can_add_a_block_override(): void
    {
        Livewire::test(ScheduleCalendar::class)
            ->set('overrideDate', '2026-12-25')
            ->set('overrideMode', 'block')
            ->set('overrideLabel', 'Holiday')
            ->call('saveOverride')
            ->assertHasNoErrors();

        $this->assertTrue(
            NightCrewScheduleWindow::query()
                ->where('kind', ScheduleWindowKind::Override)
                ->whereDate('override_date', '2026-12-25')
                ->where('override_mode', OverrideMode::Block)
                ->where('label', 'Holiday')
                ->exists()
        );
    }

    /**
     * An out-of-range weekly time is reported on the form field and nothing is saved.
     *
     * @return void
     */
    public function test_weekly_rejects_out_of_range_time_on_the_form_field(): void
    {
        $before = NightCrewScheduleWindow::query()->count();

        Livewire::test(ScheduleCalendar::class)
            ->set('weeklyStart', '25:99')
            ->set('weeklyEnd', '24:00')
            ->call('saveWeekly')
            ->assertHasErrors(['weeklyStart', 'weeklyEnd'])
            ->assertSee('The weekly start field must match the format H:i.');

        $this->assertSame($before, NightCrewScheduleWindow::query()->count());
    }

    /**
     * A replace override needs real start and end times, reported on the form fields.
     *
     * @return void
     */
    public function test_replace_override_requires_valid_times_on_the_form_fields(): void
    {
        Livewire::test(ScheduleCalendar::class)
            ->set('overrideDate', '2026-12-24')
            ->set('overrideMode', 'replace')
            ->set('overrideStart', '')
            ->set('overrideEnd', '30:00')
            ->call('saveOverride')
            ->assertHasErrors(['overrideStart', 'overrideEnd'])
            ->assertSee('The override end field must match the format H:i.');

        $this->assertFalse(
            NightCrewScheduleWindow::query()->whereDate('override_date', '2026-12-24')->exists()
        );
    }

    /**
     * A replace override with valid times stores them as minutes of the day.
     *
     * @return void
     */
    public function test_can_add_a_replace_override_with_times(): void
    {
        Livewire::test(ScheduleCalendar::class)
            ->set('overrideDate', '2026-12-26')
            ->set('overrideMode', 'replace')
            ->set('overrideStart', '09:30')
            ->set('overrideEnd', '11:00')
            ->call('saveOverride')
            ->assertHasNoErrors();

        $this->assertTrue(
            NightCrewScheduleWindow::query()
                ->whereDate('override_date', '2026-12-26')
                ->where('override_mode', OverrideMode::Replace)
                ->where('start_minute', 570)
                ->where('end_minute', 660)
                ->exists()
        );
    }

    public function test_fail_closed_banner_when_no_enabled_weekly(): void
    {
        NightCrewScheduleWindow::query()->update(['enabled' => false]);

        Livewire::test(ScheduleCalendar::class)
            ->assertSee('Fail-closed');
    }

    public function test_job_board_links_to_schedule(): void
    {
        $this->get('/')->assertOk()->assertSee('Schedule')->assertSee('/schedule', false);
    }
}
