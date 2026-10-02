<?php

declare(strict_types=1);

namespace Database\Factories;

use App\Models\Worker;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<Worker>
 */
class WorkerFactory extends Factory
{
    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'worker_id' => 'worker-'.$this->faker->unique()->word(),
            'served_repos' => ['owner/'.$this->faker->unique()->slug(2)],
        ];
    }

    /**
     * A worker that serves a specific set of repositories.
     *
     * @param  array<int, string>  $repos
     */
    public function serving(array $repos): static
    {
        return $this->state(fn (): array => [
            'served_repos' => $repos,
        ]);
    }
}
