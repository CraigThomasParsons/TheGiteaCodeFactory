<?php

declare(strict_types=1);

namespace App\Http\Resources;

use App\Models\NightCrewJob;
use App\Models\Worker;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

/**
 * API representation of a NightCrewJob.
 *
 * @mixin NightCrewJob
 */
class JobResource extends JsonResource
{
    /**
     * Transform the job into its API array.
     *
     * @param  Request  $request
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'repo' => $this->repo,
            'kind' => $this->kind->value,
            'reference' => $this->reference,
            'status' => $this->status->value,
            'priority' => $this->priority,
            'contested' => $this->contested,
            'cadence_minutes' => $this->cadence_minutes,
            'next_due_at' => optional($this->next_due_at)->toIso8601String(),
            'payload' => $this->payload,
            'claim_token' => $this->when(
                $request->user() instanceof Worker
                    && $request->user()->worker_id === $this->worker_id,
                $this->claim_token,
            ),
            'receipt' => $this->receipt,
            'created_at' => optional($this->created_at)->toIso8601String(),
        ];
    }
}
