<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Create the night_crew_jobs table — the central board of claimable work.
     */
    public function up(): void
    {
        Schema::create('night_crew_jobs', function (Blueprint $table) {
            $table->id();

            // What and where: the repository this job belongs to, its kind, and
            // (for issue jobs) the tracker reference it points at.
            $table->string('repo');
            $table->string('kind');
            $table->string('reference')->nullable();

            // Lifecycle: status plus a higher-wins priority for claim ordering.
            $table->string('status')->default('queued');
            $table->integer('priority')->default(0);

            // Opt-in flag letting several workers race the same issue job.
            $table->boolean('contested')->default(false);

            // Claim fence: which worker holds it and since when.
            $table->string('worker_id')->nullable();
            $table->timestamp('claimed_at')->nullable();

            // Recurrence: maintenance jobs record when they last ran and how
            // often they run; next_due_at is the derived, queryable "workable
            // again at" instant (issue jobs set it once, at creation).
            $table->timestamp('last_run_at')->nullable();
            $table->integer('cadence_minutes')->nullable();
            $table->timestamp('next_due_at')->nullable();

            // Arbitrary execution context handed to the client (e.g. branch slug).
            $table->json('payload')->nullable();

            $table->timestamps();

            // The claim picks the highest-priority, currently-due job for a repo.
            $table->index(['repo', 'status', 'next_due_at', 'priority']);
        });
    }

    /**
     * Drop the night_crew_jobs table.
     */
    public function down(): void
    {
        Schema::dropIfExists('night_crew_jobs');
    }
};
