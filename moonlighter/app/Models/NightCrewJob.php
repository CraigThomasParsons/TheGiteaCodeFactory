<?php

declare(strict_types=1);

namespace App\Models;

use App\Enums\JobKind;
use App\Enums\JobStatus;
use Database\Factories\NightCrewJobFactory;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Carbon;

/**
 * One claimable unit of agent work on the night-crew board.
 *
 * @property string $repo
 * @property string|null $source_key
 * @property JobKind $kind
 * @property string|null $reference
 * @property JobStatus $status
 * @property int $priority
 * @property bool $contested
 * @property string|null $worker_id
 * @property array<int, string>|null $claimed_by
 * @property Carbon|null $claimed_at
 * @property Carbon|null $last_run_at
 * @property int|null $cadence_minutes
 * @property Carbon|null $next_due_at
 * @property array<string, mixed>|null $payload
 */
class NightCrewJob extends Model
{
    /** @use HasFactory<NightCrewJobFactory> */
    use HasFactory;

    /**
     * Mass-assignable attributes. Claim/runtime fields (status, worker_id,
     * claimed_at) are set by the coordinator's own actions, never by intake.
     *
     * @var list<string>
     */
    protected $fillable = [
        'repo',
        'source_key',
        'kind',
        'reference',
        'priority',
        'contested',
        'cadence_minutes',
        'next_due_at',
        'payload',
    ];

    /**
     * Attribute casts.
     *
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'kind' => JobKind::class,
            'status' => JobStatus::class,
            'priority' => 'integer',
            'contested' => 'boolean',
            'claimed_by' => 'array',
            'claimed_at' => 'datetime',
            'last_run_at' => 'datetime',
            'cadence_minutes' => 'integer',
            'next_due_at' => 'datetime',
            'payload' => 'array',
            'receipt' => 'array',
        ];
    }

    /**
     * Scope to jobs that can be claimed right now: queued and due. A job is due
     * when its next_due_at has arrived (issue jobs set this at creation, so they
     * are due immediately; maintenance jobs set it forward after each run).
     *
     * @param  Builder<NightCrewJob>  $query
     *
     * @return Builder<NightCrewJob>
     */
    public function scopeActionable(Builder $query): Builder
    {
        return $query
            ->where('status', JobStatus::Queued)
            ->where('next_due_at', '<=', now());
    }

    /**
     * Scope to maintenance jobs whose recurrence has come due.
     *
     * @param  Builder<NightCrewJob>  $query
     *
     * @return Builder<NightCrewJob>
     */
    public function scopeDueMaintenance(Builder $query): Builder
    {
        return $query
            ->where('kind', JobKind::Maintenance)
            ->where('status', JobStatus::Queued)
            ->where('next_due_at', '<=', now());
    }

    /**
     * The list of worker identities that have already claimed this job. Ordinary
     * jobs have one; a contested issue job may have several.
     *
     * @return array<int, string>
     */
    public function claimers(): array
    {
        $claimers = $this->claimed_by;

        return is_array($claimers) ? $claimers : [];
    }

    /**
     * The canonical payload broadcast to the live dashboard when this job changes.
     *
     * @return array<string, mixed>
     */
    public function toBroadcastArray(): array
    {
        return [
            'id' => $this->id,
            'repo' => $this->repo,
            'kind' => $this->kind->value,
            'reference' => $this->reference,
            'status' => $this->status->value,
            'priority' => $this->priority,
            'contested' => $this->contested,
            'worker_id' => $this->worker_id,
            'claimed_by' => $this->claimers(),
            'next_due_at' => optional($this->next_due_at)->toIso8601String(),
        ];
    }
}
