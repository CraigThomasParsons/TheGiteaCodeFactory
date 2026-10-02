<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Create the night-crew active-hours table and seed Mon–Fri 06:00–12:00 ET.
     *
     * day_of_week uses 0 = Sunday … 6 = Saturday (Carbon-compatible).
     * start_minute / end_minute are minutes from local midnight in [0, 1440);
     * end is exclusive. When end_minute <= start_minute the window wraps overnight
     * (weekly: evening on that weekday and early morning on the next weekday).
     */
    public function up(): void
    {
        Schema::create('night_crew_schedule_windows', function (Blueprint $table) {
            $table->id();
            $table->string('kind');
            $table->string('timezone')->default('America/Toronto');
            // Weekly only: 0 = Sunday … 6 = Saturday.
            $table->unsignedTinyInteger('day_of_week')->nullable();
            // Minutes from local midnight [0, 1440); end exclusive; wrap if end <= start.
            $table->unsignedSmallInteger('start_minute')->nullable();
            $table->unsignedSmallInteger('end_minute')->nullable();
            // Override only.
            $table->date('override_date')->nullable();
            $table->string('override_mode')->nullable();
            $table->string('label')->nullable();
            $table->boolean('enabled')->default(true);
            $table->timestamps();

            $table->index(['kind', 'day_of_week']);
            $table->index(['kind', 'override_date']);
            $table->index(['enabled']);
        });

        $now = now();

        // Default crew hours: Monday–Friday 06:00–12:00 America/Toronto.
        foreach (range(1, 5) as $dayOfWeek) {
            DB::table('night_crew_schedule_windows')->insert([
                'kind' => 'weekly',
                'timezone' => 'America/Toronto',
                'day_of_week' => $dayOfWeek,
                'start_minute' => 360,
                'end_minute' => 720,
                'override_date' => null,
                'override_mode' => null,
                'label' => 'Default weekday morning',
                'enabled' => true,
                'created_at' => $now,
                'updated_at' => $now,
            ]);
        }
    }

    /**
     * Drop the schedule windows table.
     */
    public function down(): void
    {
        Schema::dropIfExists('night_crew_schedule_windows');
    }
};
