<div class="min-h-screen bg-slate-950 text-slate-100 p-6">
    <header class="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
            <h1 class="text-2xl font-semibold">Night Crew</h1>
            <p class="text-slate-400 text-sm">Live job board — updates over Reverb as workers claim and run jobs.</p>
        </div>
        <a href="{{ url('/schedule') }}"
           class="rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 text-sm">
            Schedule
        </a>
    </header>

    {{-- Add-job form: posts through the same action the intake API uses. --}}
    <form wire:submit="addJob" class="mb-8 grid gap-3 sm:grid-cols-5 items-end bg-slate-900 rounded-lg p-4">
        <label class="flex flex-col text-sm gap-1 sm:col-span-2">
            <span class="text-slate-400">Repository</span>
            <input type="text" wire:model="repo" placeholder="owner/name"
                   class="rounded bg-slate-800 border border-slate-700 px-2 py-1.5 text-sm" />
            @error('repo') <span class="text-rose-400 text-xs">{{ $message }}</span> @enderror
        </label>

        <label class="flex flex-col text-sm gap-1">
            <span class="text-slate-400">Kind</span>
            <select wire:model.live="kind"
                    class="rounded bg-slate-800 border border-slate-700 px-2 py-1.5 text-sm">
                <option value="issue">issue</option>
                <option value="maintenance">maintenance</option>
            </select>
        </label>

        @if ($kind === 'issue')
            <label class="flex flex-col text-sm gap-1">
                <span class="text-slate-400">Reference</span>
                <input type="text" wire:model="reference" placeholder="#42"
                       class="rounded bg-slate-800 border border-slate-700 px-2 py-1.5 text-sm" />
                @error('reference') <span class="text-rose-400 text-xs">{{ $message }}</span> @enderror
            </label>
        @else
            <label class="flex flex-col text-sm gap-1">
                <span class="text-slate-400">Cadence (min)</span>
                <input type="number" min="1" wire:model="cadenceMinutes" placeholder="1440"
                       class="rounded bg-slate-800 border border-slate-700 px-2 py-1.5 text-sm" />
                @error('cadenceMinutes') <span class="text-rose-400 text-xs">{{ $message }}</span> @enderror
            </label>
        @endif

        <button type="submit"
                class="rounded bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 text-sm font-medium">
            Add job
        </button>
    </form>

    {{-- One column per lifecycle status. --}}
    <div class="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
        @foreach ($this->statuses() as $status)
            @php($jobs = $jobsByStatus->get($status, collect()))
            <section class="bg-slate-900 rounded-lg p-3">
                <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-3 flex justify-between">
                    <span>{{ $status }}</span>
                    <span class="text-slate-500">{{ $jobs->count() }}</span>
                </h2>

                <div class="space-y-2">
                    @forelse ($jobs as $job)
                        <article wire:key="job-{{ $job->id }}"
                                 class="rounded border border-slate-800 bg-slate-800/50 p-2 text-sm">
                            <div class="flex justify-between gap-2">
                                <span class="font-medium truncate">{{ $job->repo }}</span>
                                <span class="text-slate-400">{{ $job->kind->value }}</span>
                            </div>
                            @if ($job->reference)
                                <div class="text-slate-400 text-xs">{{ $job->reference }}</div>
                            @endif
                            @if ($job->worker_id)
                                <div class="text-emerald-400 text-xs">⛏ {{ $job->worker_id }}</div>
                            @endif
                            @if ($job->contested)
                                <div class="text-amber-400 text-xs">contested · {{ count($job->claimers()) }} claim(s)</div>
                            @endif
                        </article>
                    @empty
                        <p class="text-slate-600 text-xs italic">empty</p>
                    @endforelse
                </div>
            </section>
        @endforeach
    </div>
</div>
