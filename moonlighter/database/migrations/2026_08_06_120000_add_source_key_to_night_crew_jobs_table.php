<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Add a caller-owned idempotency key for externally discovered work.
     */
    public function up(): void
    {
        Schema::table('night_crew_jobs', function (Blueprint $table): void {
            // Nullable keeps manually submitted and recurring jobs unchanged;
            // discovered tickets receive a stable, database-enforced identity.
            $table->string('source_key')->nullable()->unique();
        });
    }

    /**
     * Remove the external-source identity from queued jobs.
     */
    public function down(): void
    {
        Schema::table('night_crew_jobs', function (Blueprint $table): void {
            $table->dropUnique(['source_key']);
            $table->dropColumn('source_key');
        });
    }
};
