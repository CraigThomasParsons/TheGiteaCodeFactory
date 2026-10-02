<?php

declare(strict_types=1);

namespace Database\Factories;

use App\Enums\JobKind;
use App\Enums\JobStatus;
use App\Models\NightCrewJob;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<NightCrewJob>
 */
class NightCrewJobFactory extends Factory
{
    /**
     * Default state: a queued, immediately-due issue job.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'repo' => $this->faker->unique()->slug(2),
            'kind' => JobKind::Issue,
            'reference' => '#'.$this->faker->numberBetween(1, 999),
            'status' => JobStatus::Queued,
            'priority' => 0,
            'contested' => false,
            'worker_id' => null,
            'claimed_at' => null,
            'last_run_at' => null,
            'cadence_minutes' => null,
            'next_due_at' => now(),
            'payload' => null,
        ];
    }

    /**
     * A job belonging to a specific repository.
     *
     * @param  string  $repo
     */
    public function forRepo(string $repo): static
    {
        return $this->state(fn (): array => [
            'repo' => $repo,
        ]);
    }

    /**
     * A recurring maintenance job that is currently due.
     */
    public function maintenanceDue(): static
    {
        return $this->state(fn (): array => [
            'kind' => JobKind::Maintenance,
            'reference' => null,
            'cadence_minutes' => 1440,
            'last_run_at' => now()->subDays(2),
            'next_due_at' => now()->subMinutes(5),
        ]);
    }

    /**
     * A recurring maintenance job that is not yet due.
     */
    public function maintenanceNotDue(): static
    {
        return $this->state(fn (): array => [
            'kind' => JobKind::Maintenance,
            'reference' => null,
            'cadence_minutes' => 1440,
            'last_run_at' => now()->subHours(1),
            'next_due_at' => now()->addHours(23),
        ]);
    }

    /**
     * A job already claimed by a worker.
     */
    public function claimed(): static
    {
        return $this->state(fn (): array => [
            'status' => JobStatus::Claimed,
            'worker_id' => 'worker-'.$this->faker->word(),
            'claimed_at' => now(),
        ]);
    }

    /**
     * A finished issue job.
     */
    public function done(): static
    {
        return $this->state(fn (): array => [
            'status' => JobStatus::Done,
        ]);
    }

    /**
     * Mark the job contested (issue jobs only).
     */
    public function contested(): static
    {
        return $this->state(fn (): array => [
            'contested' => true,
        ]);
    }

    /**
     * A job claimed by a specific worker.
     *
     * @param  string  $workerId
     */
    public function claimedBy(string $workerId): static
    {
        return $this->state(fn (): array => [
            'status' => JobStatus::Claimed,
            'worker_id' => $workerId,
            'claimed_by' => [$workerId],
            'claimed_at' => now(),
        ]);
    }

    /**
     * A job a specific worker is actively running.
     *
     * @param  string  $workerId
     */
    public function runningBy(string $workerId): static
    {
        return $this->state(fn (): array => [
            'status' => JobStatus::Running,
            'worker_id' => $workerId,
            'claimed_by' => [$workerId],
            'claimed_at' => now(),
        ]);
    }
}
