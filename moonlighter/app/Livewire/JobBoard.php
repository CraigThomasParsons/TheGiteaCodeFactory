<?php

declare(strict_types=1);

namespace App\Livewire;

use App\Actions\Jobs\CreateJobAction;
use App\Enums\JobKind;
use App\Enums\JobStatus;
use App\Models\NightCrewJob;
use Illuminate\Contracts\View\View;
use Illuminate\Support\Arr;
use Illuminate\Validation\Rule;
use Livewire\Attributes\On;
use Livewire\Attributes\Title;
use Livewire\Component;

/**
 * The live night-crew board: a list of jobs grouped by status that updates over
 * Reverb, plus a simple form for adding a job by hand.
 */
#[Title('Night Crew')]
class JobBoard extends Component
{
    /**
     * Add-job form: the repository the job is for.
     */
    public string $repo = '';

    /**
     * Add-job form: issue or maintenance.
     */
    public string $kind = 'issue';

    /**
     * Add-job form: the tracker reference (issue jobs).
     */
    public string $reference = '';

    /**
     * Add-job form: minutes between runs (maintenance jobs).
     */
    public ?int $cadenceMinutes = null;

    /**
     * The statuses rendered as columns, in lifecycle order.
     *
     * @return array<int, string>
     */
    public function statuses(): array
    {
        return [
            JobStatus::Queued->value,
            JobStatus::Claimed->value,
            JobStatus::Running->value,
            JobStatus::Done->value,
            JobStatus::Failed->value,
        ];
    }

    /**
     * Add a job from the form, delegating creation to the shared action.
     *
     * @param  CreateJobAction  $createJob
     */
    public function addJob(CreateJobAction $createJob): void
    {
        $validated = $this->validate([
            'repo' => ['required', 'string', 'max:255'],
            'kind' => ['required', Rule::enum(JobKind::class)],
            'reference' => ['nullable', 'string', 'max:255', Rule::requiredIf($this->kind === JobKind::Issue->value)],
            'cadenceMinutes' => ['nullable', 'integer', 'min:1', Rule::requiredIf($this->kind === JobKind::Maintenance->value)],
        ]);

        $createJob->handle($validated['repo'], [
            'kind' => $validated['kind'],
            'reference' => Arr::get($validated, 'reference'),
            'cadence_minutes' => Arr::get($validated, 'cadenceMinutes'),
        ]);

        // Clear the form; the board re-renders with the new job in place.
        $this->reset(['repo', 'reference', 'cadenceMinutes']);
        $this->kind = 'issue';
    }

    /**
     * Re-render when any job event arrives over the night-crew channel. The dot
     * prefixes match the events' broadcastAs() names.
     */
    #[On('echo:night-crew,.job.created')]
    #[On('echo:night-crew,.job.claimed')]
    #[On('echo:night-crew,.job.status-changed')]
    public function onBoardChanged(): void
    {
        // No state to mutate: returning triggers a re-render with fresh data.
    }

    /**
     * Render the board with every job grouped by status.
     */
    public function render(): View
    {
        $jobsByStatus = NightCrewJob::query()
            ->orderByDesc('priority')
            ->orderBy('id')
            ->get()
            ->groupBy(fn (NightCrewJob $job): string => $job->status->value);

        return view('livewire.job-board', [
            'jobsByStatus' => $jobsByStatus,
        ]);
    }
}
