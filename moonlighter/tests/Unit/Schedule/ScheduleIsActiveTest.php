<?php

declare(strict_types=1);

namespace Tests\Unit\Schedule;

use App\Enums\OverrideMode;
use App\Models\NightCrewScheduleWindow;
use App\Services\Schedule;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use Tests\TestCase;

class ScheduleIsActiveTest extends TestCase
{
    use RefreshDatabase;

    private Schedule $schedule;

    protected function setUp(): void
    {
        parent::setUp();
        $this->schedule = new Schedule;
        // Drop migration seed so each case controls its own windows.
        NightCrewScheduleWindow::query()->delete();
    }

    protected function tearDown(): void
    {
        Carbon::setTestNow();
        parent::tearDown();
    }

    /**
     * Monday 09:00 America/Toronto is inside a Mon 06:00–12:00 weekly window.
     */
    public function test_weekly_active_inside_window(): void
    {
        NightCrewScheduleWindow::factory()->weekly(1, 360, 720)->create();

        // 2026-09-21 is a Monday; 13:00 UTC = 09:00 EDT (UTC-4).
        Carbon::setTestNow(Carbon::parse('2026-09-21 13:00:00', 'UTC'));

        $this->assertTrue($this->schedule->isActive());
    }

    /**
     * Monday 13:00 America/Toronto is outside Mon 06:00–12:00.
     */
    public function test_weekly_inactive_outside_window(): void
    {
        NightCrewScheduleWindow::factory()->weekly(1, 360, 720)->create();

        // 17:00 UTC = 13:00 EDT.
        Carbon::setTestNow(Carbon::parse('2026-09-21 17:00:00', 'UTC'));

        $this->assertFalse($this->schedule->isActive());
    }

    /**
     * Empty enabled weekly set is fail-closed.
     */
    public function test_fail_closed_with_no_enabled_weekly_windows(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-09-21 13:00:00', 'UTC'));

        $this->assertFalse($this->schedule->isActive());
        $this->assertFalse($this->schedule->hasEnabledWeeklyWindows());
    }

    /**
     * Disabled weekly rows do not count — still fail-closed.
     */
    public function test_disabled_weekly_does_not_activate(): void
    {
        NightCrewScheduleWindow::factory()->weekly(1, 360, 720)->disabled()->create();
        Carbon::setTestNow(Carbon::parse('2026-09-21 13:00:00', 'UTC'));

        $this->assertFalse($this->schedule->isActive());
    }

    /**
     * Overnight wrap: Fri 22:00–06:00 is active at Friday 23:00 and Saturday 01:00, not Saturday 07:00.
     */
    public function test_overnight_wrap(): void
    {
        // Friday (5) 22:00 → Saturday 06:00 (end exclusive).
        NightCrewScheduleWindow::factory()->weekly(5, 22 * 60, 6 * 60)->create();
        // Disabled Saturday row so emptiness alone is not why Saturday morning fails.
        NightCrewScheduleWindow::factory()->weekly(6, 0, 0)->disabled()->create();

        Carbon::setTestNow(Carbon::parse('2026-09-26 03:00:00', 'UTC')); // Fri 23:00 EDT
        $this->assertTrue($this->schedule->isActive(), 'Friday 23:00 should be active');

        // Saturday 01:00 EDT: Friday's overnight wrap continues into Saturday morning.
        Carbon::setTestNow(Carbon::parse('2026-09-26 05:00:00', 'UTC')); // Sat 01:00 EDT
        $this->assertTrue($this->schedule->isActive(), 'Saturday 01:00 should be covered by Friday overnight wrap');

        Carbon::setTestNow(Carbon::parse('2026-09-26 11:00:00', 'UTC')); // Sat 07:00 EDT
        $this->assertFalse($this->schedule->isActive(), 'Saturday 07:00 is past the wrap end');

        Carbon::setTestNow(Carbon::parse('2026-09-26 01:00:00', 'UTC')); // Fri 21:00 EDT
        $this->assertFalse($this->schedule->isActive(), 'Friday 21:00 should be inactive');
    }

    /**
     * Same-weekday early half: a Sunday 22:00-06:00 row covers only Sunday
     * 22:00 onward on its own weekday; the early half belongs to Monday
     * morning via the previous-weekday overnight carry.
     */
    public function test_overnight_wrap_does_not_cover_early_morning_same_weekday(): void
    {
        // Sunday (0) 22:00-06:00: active Sun 22:00-23:59 and Mon 00:00-05:59.
        NightCrewScheduleWindow::factory()->weekly(0, 22 * 60, 6 * 60)->create();

        // Sunday 01:00 EDT = 2026-09-27 05:00 UTC (2026-09-27 is Sunday).
        Carbon::setTestNow(Carbon::parse('2026-09-27 05:00:00', 'UTC'));
        $this->assertFalse($this->schedule->isActive(), 'Sunday 01:00 is before the Sunday shift starts');

        // Sunday 23:00 EDT = 2026-09-28 03:00 UTC.
        Carbon::setTestNow(Carbon::parse('2026-09-28 03:00:00', 'UTC'));
        $this->assertTrue($this->schedule->isActive(), 'Sunday 23:00 is inside the Sunday shift');

        // Monday 01:00 EDT: Sunday overnight carries into Monday morning.
        Carbon::setTestNow(Carbon::parse('2026-09-28 05:00:00', 'UTC'));
        $this->assertTrue($this->schedule->isActive(), 'Monday 01:00 should be covered by Sunday overnight wrap');

        // Monday 07:00 EDT, past the carried end.
        Carbon::setTestNow(Carbon::parse('2026-09-28 11:00:00', 'UTC'));
        $this->assertFalse($this->schedule->isActive(), 'Monday 07:00 is past the wrap end');
    }

    public function test_block_override_forces_inactive(): void
    {
        NightCrewScheduleWindow::factory()->weekly(1, 360, 720)->create();
        NightCrewScheduleWindow::factory()
            ->override('2026-09-21', OverrideMode::Block)
            ->create();

        Carbon::setTestNow(Carbon::parse('2026-09-21 13:00:00', 'UTC')); // Mon 09:00 ET
        $this->assertFalse($this->schedule->isActive());
    }

    public function test_replace_override_ignores_weekly(): void
    {
        NightCrewScheduleWindow::factory()->weekly(1, 360, 720)->create(); // Mon 06–12
        NightCrewScheduleWindow::factory()
            ->override('2026-09-21', OverrideMode::Replace, 14 * 60, 16 * 60) // 14–16
            ->create();

        // Inside weekly but outside replace → inactive.
        Carbon::setTestNow(Carbon::parse('2026-09-21 13:00:00', 'UTC')); // 09:00 ET
        $this->assertFalse($this->schedule->isActive());

        // Outside weekly, inside replace → active.
        Carbon::setTestNow(Carbon::parse('2026-09-21 19:00:00', 'UTC')); // 15:00 ET
        $this->assertTrue($this->schedule->isActive());
    }

    public function test_extend_override_ors_with_weekly(): void
    {
        NightCrewScheduleWindow::factory()->weekly(1, 360, 720)->create(); // Mon 06–12
        NightCrewScheduleWindow::factory()
            ->override('2026-09-21', OverrideMode::Extend, 18 * 60, 20 * 60) // 18–20
            ->create();

        // Weekly window still active.
        Carbon::setTestNow(Carbon::parse('2026-09-21 13:00:00', 'UTC')); // 09:00 ET
        $this->assertTrue($this->schedule->isActive());

        // Extend window active.
        Carbon::setTestNow(Carbon::parse('2026-09-21 23:00:00', 'UTC')); // 19:00 ET
        $this->assertTrue($this->schedule->isActive());

        // Neither.
        Carbon::setTestNow(Carbon::parse('2026-09-21 17:00:00', 'UTC')); // 13:00 ET
        $this->assertFalse($this->schedule->isActive());
    }

    /**
     * A Friday block cancels the whole overnight shift: Friday evening is
     * inactive (today's block) and Saturday morning carry is dropped.
     */
    public function test_friday_block_stops_saturday_overnight_carry(): void
    {
        NightCrewScheduleWindow::factory()->weekly(5, 22 * 60, 6 * 60)->create(); // Fri overnight
        NightCrewScheduleWindow::factory()
            ->override('2026-09-25', OverrideMode::Block) // Friday local date
            ->create();

        Carbon::setTestNow(Carbon::parse('2026-09-26 03:00:00', 'UTC')); // Fri 23:00 EDT
        $this->assertFalse(
            $this->schedule->isActive(),
            'Friday evening is blocked as the override local date',
        );

        Carbon::setTestNow(Carbon::parse('2026-09-26 05:00:00', 'UTC')); // Sat 01:00 EDT
        $this->assertFalse(
            $this->schedule->isActive(),
            'Friday block cancels Saturday morning carry of the overnight shift',
        );
    }

    /**
     * A Saturday block also stops Saturday morning carry from Friday overnight,
     * because today's block governs the whole Saturday local date (independent
     * of whether Friday itself was blocked).
     */
    public function test_saturday_block_stops_friday_overnight_carry(): void
    {
        NightCrewScheduleWindow::factory()->weekly(5, 22 * 60, 6 * 60)->create(); // Fri overnight
        NightCrewScheduleWindow::factory()
            ->override('2026-09-26', OverrideMode::Block) // Saturday local date
            ->create();

        Carbon::setTestNow(Carbon::parse('2026-09-26 05:00:00', 'UTC')); // Sat 01:00 EDT
        $this->assertFalse(
            $this->schedule->isActive(),
            'Saturday block governs the local date and stops the Friday carry',
        );

        Carbon::setTestNow(Carbon::parse('2026-09-26 03:00:00', 'UTC')); // Fri 23:00 EDT
        $this->assertTrue($this->schedule->isActive(), 'Friday own-day portion is unaffected by a Saturday block');
    }

    /**
     * A Saturday extend still ORs with weekly rules when Friday was not blocked,
     * so the Friday overnight carry keeps Saturday morning active alongside the
     * extend window.
     */
    public function test_saturday_extend_keeps_friday_overnight_carry(): void
    {
        NightCrewScheduleWindow::factory()->weekly(5, 22 * 60, 6 * 60)->create(); // Fri overnight
        NightCrewScheduleWindow::factory()
            ->override('2026-09-26', OverrideMode::Extend, 14 * 60, 16 * 60) // Sat 14-16
            ->create();

        Carbon::setTestNow(Carbon::parse('2026-09-26 05:00:00', 'UTC')); // Sat 01:00 EDT
        $this->assertTrue(
            $this->schedule->isActive(),
            'Saturday extend ORs with weekly, which includes the Friday carry',
        );

        Carbon::setTestNow(Carbon::parse('2026-09-26 19:00:00', 'UTC')); // Sat 15:00 EDT
        $this->assertTrue($this->schedule->isActive(), 'Saturday extend window itself is active');

        Carbon::setTestNow(Carbon::parse('2026-09-26 11:00:00', 'UTC')); // Sat 07:00 EDT
        $this->assertFalse($this->schedule->isActive(), 'Saturday 07:00 is past the carry and outside the extend');
    }

    /**
     * A Saturday replace drops Friday overnight carry for Saturday morning.
     */
    public function test_saturday_replace_drops_friday_overnight_carry(): void
    {
        NightCrewScheduleWindow::factory()->weekly(5, 22 * 60, 6 * 60)->create(); // Fri overnight
        NightCrewScheduleWindow::factory()
            ->override('2026-09-26', OverrideMode::Replace, 14 * 60, 16 * 60) // Sat 14-16
            ->create();

        Carbon::setTestNow(Carbon::parse('2026-09-26 05:00:00', 'UTC')); // Sat 01:00 EDT
        $this->assertFalse(
            $this->schedule->isActive(),
            'Saturday replace governs the local date and drops the Friday carry',
        );

        Carbon::setTestNow(Carbon::parse('2026-09-26 19:00:00', 'UTC')); // Sat 15:00 EDT
        $this->assertTrue($this->schedule->isActive(), 'Saturday replace window itself is active');
    }

    /**
     * Only a block on the start date cancels the carry: a Friday replace
     * governs Friday itself but leaves Saturday morning carry of Friday's
     * overnight weekly row in place.
     */
    public function test_friday_replace_keeps_saturday_overnight_carry(): void
    {
        NightCrewScheduleWindow::factory()->weekly(5, 22 * 60, 6 * 60)->create(); // Fri overnight
        NightCrewScheduleWindow::factory()
            ->override('2026-09-25', OverrideMode::Replace, 14 * 60, 16 * 60) // Fri 14-16
            ->create();

        Carbon::setTestNow(Carbon::parse('2026-09-26 03:00:00', 'UTC')); // Fri 23:00 EDT
        $this->assertFalse(
            $this->schedule->isActive(),
            'Friday replace governs the Friday local date',
        );

        Carbon::setTestNow(Carbon::parse('2026-09-26 05:00:00', 'UTC')); // Sat 01:00 EDT
        $this->assertTrue(
            $this->schedule->isActive(),
            'A non-block override on Friday does not cancel Saturday morning carry',
        );
    }
}
