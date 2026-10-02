<div class="min-h-screen bg-slate-950 text-slate-100 p-6">
    <header class="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
            <h1 class="text-2xl font-semibold">Schedule</h1>
            <p class="text-slate-400 text-sm">Active claiming windows — workers receive no jobs outside these hours.</p>
        </div>
        <div class="flex items-center gap-2 text-sm">
            <span class="rounded-full bg-slate-800 border border-slate-700 px-3 py-1 text-slate-300">
                {{ $timezone }}
            </span>
            @if ($isActiveNow)
                <span class="rounded-full bg-emerald-900/60 border border-emerald-700 px-3 py-1 text-emerald-300">active now</span>
            @else
                <span class="rounded-full bg-rose-900/60 border border-rose-700 px-3 py-1 text-rose-300">inactive now</span>
            @endif
            <a href="{{ url('/') }}" class="rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5">← Job board</a>
        </div>
    </header>

    @if ($failClosed)
        <div class="mb-6 rounded-lg border border-amber-700 bg-amber-950/50 px-4 py-3 text-amber-200 text-sm">
            <strong class="font-semibold">Fail-closed:</strong> no enabled weekly windows — claiming is blocked until at least one weekly row is enabled.
        </div>
    @endif

    {{-- Monday-first weekly strip --}}
    <section class="mb-8">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-3">This week</h2>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
            @foreach ($weekDays as $day)
                <div class="bg-slate-900 rounded-lg p-3 border border-slate-800">
                    <div class="flex justify-between text-sm mb-2">
                        <span class="font-medium">{{ $day['label'] }}</span>
                        <span class="text-slate-500 text-xs">{{ $day['date'] }}</span>
                    </div>
                    <div class="space-y-1">
                        @forelse ($day['windows'] as $window)
                            <button type="button"
                                    wire:click="editWeekly({{ $window->id }})"
                                    wire:key="week-win-{{ $window->id }}"
                                    class="w-full text-left rounded border px-2 py-1 text-xs
                                           {{ $window->enabled ? 'border-indigo-700 bg-indigo-950/40 text-indigo-200' : 'border-slate-700 bg-slate-800/40 text-slate-500 line-through' }}">
                                {{ sprintf('%02d:%02d', intdiv($window->start_minute, 60), $window->start_minute % 60) }}
                                –
                                {{ sprintf('%02d:%02d', intdiv($window->end_minute, 60), $window->end_minute % 60) }}
                                @if ($window->end_minute <= $window->start_minute)
                                    <span class="text-amber-400">(overnight)</span>
                                @endif
                            </button>
                        @empty
                            <p class="text-slate-600 text-xs italic">no window</p>
                        @endforelse
                    </div>
                </div>
            @endforeach
        </div>
    </section>

    <div class="grid gap-6 lg:grid-cols-2">
        {{-- Weekly editor --}}
        <section class="bg-slate-900 rounded-lg p-4 border border-slate-800">
            <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-3">
                {{ $weeklyId ? 'Edit weekly window' : 'Add weekly window' }}
            </h2>
            <form wire:submit="saveWeekly" class="grid gap-3 sm:grid-cols-2">
                <label class="flex flex-col text-sm gap-1">
                    <span class="text-slate-400">Day</span>
                    <select wire:model="weeklyDayOfWeek" class="rounded bg-slate-800 border border-slate-700 px-2 py-1.5 text-sm">
                        @foreach ([1,2,3,4,5,6,0] as $dow)
                            <option value="{{ $dow }}">{{ $dayLabels[$dow] }} ({{ $dow }})</option>
                        @endforeach
                    </select>
                    @error('weeklyDayOfWeek') <span class="text-rose-400 text-xs">{{ $message }}</span> @enderror
                </label>
                <label class="flex flex-col text-sm gap-1">
                    <span class="text-slate-400">Label</span>
                    <input type="text" wire:model="weeklyLabel" class="rounded bg-slate-800 border border-slate-700 px-2 py-1.5 text-sm" />
                </label>
                <label class="flex flex-col text-sm gap-1">
                    <span class="text-slate-400">Start</span>
                    <input type="time" wire:model="weeklyStart" class="rounded bg-slate-800 border border-slate-700 px-2 py-1.5 text-sm" />
                    @error('weeklyStart') <span class="text-rose-400 text-xs">{{ $message }}</span> @enderror
                </label>
                <label class="flex flex-col text-sm gap-1">
                    <span class="text-slate-400">End (exclusive)</span>
                    <input type="time" wire:model="weeklyEnd" class="rounded bg-slate-800 border border-slate-700 px-2 py-1.5 text-sm" />
                    @error('weeklyEnd') <span class="text-rose-400 text-xs">{{ $message }}</span> @enderror
                </label>
                <label class="flex items-center gap-2 text-sm sm:col-span-2">
                    <input type="checkbox" wire:model="weeklyEnabled" class="rounded border-slate-600 bg-slate-800" />
                    <span class="text-slate-300">Enabled</span>
                </label>
                <div class="sm:col-span-2 flex flex-wrap gap-2">
                    <button type="submit" class="rounded bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 text-sm font-medium">
                        {{ $weeklyId ? 'Update' : 'Add' }} weekly
                    </button>
                    @if ($weeklyId)
                        <button type="button" wire:click="resetWeeklyForm" class="rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 text-sm">Cancel</button>
                        <button type="button" wire:click="deleteWindow({{ $weeklyId }})" wire:confirm="Delete this weekly window?"
                                class="rounded bg-rose-800 hover:bg-rose-700 px-3 py-1.5 text-sm">Delete</button>
                    @endif
                </div>
            </form>
            <p class="mt-3 text-xs text-slate-500">If end ≤ start, the window wraps overnight into the next morning. day_of_week: 0=Sun … 6=Sat.</p>
        </section>

        {{-- Overrides panel --}}
        <section class="bg-slate-900 rounded-lg p-4 border border-slate-800">
            <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-3">
                {{ $overrideId ? 'Edit override' : 'Add override' }}
            </h2>
            <form wire:submit="saveOverride" class="grid gap-3 sm:grid-cols-2">
                <label class="flex flex-col text-sm gap-1">
                    <span class="text-slate-400">Date</span>
                    <input type="date" wire:model="overrideDate" class="rounded bg-slate-800 border border-slate-700 px-2 py-1.5 text-sm" />
                    @error('overrideDate') <span class="text-rose-400 text-xs">{{ $message }}</span> @enderror
                </label>
                <label class="flex flex-col text-sm gap-1">
                    <span class="text-slate-400">Mode</span>
                    <select wire:model.live="overrideMode" class="rounded bg-slate-800 border border-slate-700 px-2 py-1.5 text-sm">
                        <option value="block">block (force off)</option>
                        <option value="replace">replace (only this window)</option>
                        <option value="extend">extend (weekly OR this)</option>
                    </select>
                    @error('overrideMode') <span class="text-rose-400 text-xs">{{ $message }}</span> @enderror
                </label>
                @if ($overrideMode !== 'block')
                    <label class="flex flex-col text-sm gap-1">
                        <span class="text-slate-400">Start</span>
                        <input type="time" wire:model="overrideStart" class="rounded bg-slate-800 border border-slate-700 px-2 py-1.5 text-sm" />
                        @error('overrideStart') <span class="text-rose-400 text-xs">{{ $message }}</span> @enderror
                    </label>
                    <label class="flex flex-col text-sm gap-1">
                        <span class="text-slate-400">End (exclusive)</span>
                        <input type="time" wire:model="overrideEnd" class="rounded bg-slate-800 border border-slate-700 px-2 py-1.5 text-sm" />
                        @error('overrideEnd') <span class="text-rose-400 text-xs">{{ $message }}</span> @enderror
                    </label>
                @endif
                <label class="flex flex-col text-sm gap-1 sm:col-span-2">
                    <span class="text-slate-400">Label</span>
                    <input type="text" wire:model="overrideLabel" class="rounded bg-slate-800 border border-slate-700 px-2 py-1.5 text-sm" />
                </label>
                <label class="flex items-center gap-2 text-sm sm:col-span-2">
                    <input type="checkbox" wire:model="overrideEnabled" class="rounded border-slate-600 bg-slate-800" />
                    <span class="text-slate-300">Enabled</span>
                </label>
                <div class="sm:col-span-2 flex flex-wrap gap-2">
                    <button type="submit" class="rounded bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 text-sm font-medium">
                        {{ $overrideId ? 'Update' : 'Add' }} override
                    </button>
                    @if ($overrideId)
                        <button type="button" wire:click="resetOverrideForm" class="rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 text-sm">Cancel</button>
                        <button type="button" wire:click="deleteWindow({{ $overrideId }})" wire:confirm="Delete this override?"
                                class="rounded bg-rose-800 hover:bg-rose-700 px-3 py-1.5 text-sm">Delete</button>
                    @endif
                </div>
            </form>
            <p class="mt-3 text-xs text-slate-500">To cancel an overnight shift including the next morning wrap, block the night&apos;s start date (for example a Friday block covers Friday evening and Saturday morning).</p>

            <h3 class="mt-6 text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">Overrides</h3>
            <div class="space-y-2 max-h-64 overflow-y-auto">
                @forelse ($overrides as $window)
                    <article wire:key="ov-{{ $window->id }}"
                             class="rounded border border-slate-800 bg-slate-800/40 p-2 text-sm flex justify-between gap-2">
                        <button type="button" wire:click="editOverride({{ $window->id }})" class="text-left flex-1">
                            <div class="font-medium">
                                {{ $window->override_date?->toDateString() }}
                                <span class="text-slate-400">· {{ $window->override_mode?->value }}</span>
                                @unless ($window->enabled)
                                    <span class="text-slate-500">(disabled)</span>
                                @endunless
                            </div>
                            @if ($window->override_mode?->value !== 'block' && $window->start_minute !== null)
                                <div class="text-xs text-slate-400">
                                    {{ sprintf('%02d:%02d', intdiv($window->start_minute, 60), $window->start_minute % 60) }}
                                    –
                                    {{ sprintf('%02d:%02d', intdiv($window->end_minute, 60), $window->end_minute % 60) }}
                                </div>
                            @endif
                            @if ($window->label)
                                <div class="text-xs text-slate-500">{{ $window->label }}</div>
                            @endif
                        </button>
                        <button type="button" wire:click="deleteWindow({{ $window->id }})" wire:confirm="Delete this override?"
                                class="text-rose-400 hover:text-rose-300 text-xs self-start">delete</button>
                    </article>
                @empty
                    <p class="text-slate-600 text-xs italic">no overrides</p>
                @endforelse
            </div>
        </section>
    </div>
</div>
