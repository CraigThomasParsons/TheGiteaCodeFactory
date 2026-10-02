<?php

declare(strict_types=1);

namespace Tests\Unit\Schedule;

use App\Actions\Schedule\ScheduleWindowGuard;
use App\Enums\OverrideMode;
use App\Enums\ScheduleWindowKind;
use App\Models\NightCrewScheduleWindow;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Validation\ValidationException;
use Tests\TestCase;

class ScheduleWindowGuardTest extends TestCase
{
    use RefreshDatabase;

    private ScheduleWindowGuard $guard;

    /**
     * Build the guard under test.
     *
     * @return void
     */
    protected function setUp(): void
    {
        parent::setUp();
        $this->guard = new ScheduleWindowGuard;
    }

    /**
     * Minutes 0 and 1439 are the inclusive bounds of a local day.
     *
     * @return void
     */
    public function test_accepts_minutes_inside_the_day(): void
    {
        $this->guard->assertMinute(0, 'start_minute');
        $this->guard->assertMinute(1439, 'end_minute');

        $this->addToAssertionCount(2);
    }

    /**
     * Minute 1440 is the exclusive upper bound and is rejected under the given key.
     *
     * @return void
     */
    public function test_rejects_minute_1440_under_the_given_field(): void
    {
        try {
            $this->guard->assertMinute(1440, 'end_minute');
            $this->fail('Expected a ValidationException.');
        } catch (ValidationException $exception) {
            $this->assertArrayHasKey('end_minute', $exception->errors());
        }
    }

    /**
     * Negative minutes are rejected.
     *
     * @return void
     */
    public function test_rejects_negative_minute(): void
    {
        $this->expectException(ValidationException::class);

        $this->guard->assertMinute(-1, 'start_minute');
    }

    /**
     * A null id yields an unsaved row.
     *
     * @return void
     */
    public function test_null_id_returns_new_window(): void
    {
        $window = $this->guard->findOrNewOfKind(null, ScheduleWindowKind::Weekly, 'wrong kind');

        $this->assertFalse($window->exists);
    }

    /**
     * An existing row of the requested kind is returned for update.
     *
     * @return void
     */
    public function test_returns_existing_window_of_same_kind(): void
    {
        $existing = NightCrewScheduleWindow::factory()->weekly(2)->create();

        $window = $this->guard->findOrNewOfKind($existing->id, ScheduleWindowKind::Weekly, 'wrong kind');

        $this->assertTrue($window->is($existing));
    }

    /**
     * Upserting an override id as weekly is refused under the `id` key.
     *
     * @return void
     */
    public function test_rejects_existing_window_of_other_kind(): void
    {
        $override = NightCrewScheduleWindow::factory()->override('2026-12-25', OverrideMode::Block)->create();

        try {
            $this->guard->findOrNewOfKind($override->id, ScheduleWindowKind::Weekly, 'wrong kind');
            $this->fail('Expected a ValidationException.');
        } catch (ValidationException $exception) {
            $this->assertSame(['wrong kind'], $exception->errors()['id']);
        }
    }
}
