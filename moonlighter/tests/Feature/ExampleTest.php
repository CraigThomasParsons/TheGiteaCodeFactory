<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Livewire\JobBoard;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ExampleTest extends TestCase
{
    use RefreshDatabase;

    /**
     * The home page renders the live job board component.
     */
    public function test_the_home_page_renders_the_job_board(): void
    {
        // Skip the Vite manifest so the smoke test does not depend on a build.
        $this->withoutVite();

        $this->get('/')
            ->assertOk()
            ->assertSeeLivewire(JobBoard::class);
    }
}
