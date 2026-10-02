<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Create the workers table — one row per computer that runs night-crew work.
     */
    public function up(): void
    {
        Schema::create('workers', function (Blueprint $table) {
            $table->id();

            // Stable identity (for example, the hostname) used to stamp claims.
            $table->string('worker_id')->unique();

            // The repositories this worker is able to run; jobs are only ever
            // offered to a worker that serves the job's repo.
            $table->json('served_repos');

            $table->timestamps();
        });
    }

    /**
     * Drop the workers table.
     */
    public function down(): void
    {
        Schema::dropIfExists('workers');
    }
};
