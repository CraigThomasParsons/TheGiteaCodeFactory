<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /** Add fenced receipts without changing existing issue jobs. */
    public function up(): void
    {
        Schema::table('night_crew_jobs', function (Blueprint $table): void {
            $table->uuid('claim_token')->nullable();
            $table->json('receipt')->nullable();
        });
    }

    /** Remove PR receipt storage. */
    public function down(): void
    {
        Schema::table('night_crew_jobs', function (Blueprint $table): void {
            $table->dropColumn(['claim_token', 'receipt']);
        });
    }
};
