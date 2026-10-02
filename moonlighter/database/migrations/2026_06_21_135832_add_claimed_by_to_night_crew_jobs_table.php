<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Record every worker that has claimed a job. For an ordinary job this holds
     * a single worker; for a contested issue job several workers may each claim
     * it, which a single worker_id column cannot represent.
     */
    public function up(): void
    {
        Schema::table('night_crew_jobs', function (Blueprint $table) {
            $table->json('claimed_by')->nullable()->after('worker_id');
        });
    }

    /**
     * Drop the claimed_by column.
     */
    public function down(): void
    {
        Schema::table('night_crew_jobs', function (Blueprint $table) {
            $table->dropColumn('claimed_by');
        });
    }
};
