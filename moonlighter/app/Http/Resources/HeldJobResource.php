<?php

declare(strict_types=1);

namespace App\Http\Resources;

use Illuminate\Http\Request;

/**
 * A job as seen by the worker that holds it: the ordinary job representation
 * plus the claim fields a local bridge needs to reconcile its own ledger.
 */
class HeldJobResource extends JobResource
{
    /**
     * Transform the held job into its API array.
     *
     * @param  Request  $request
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        return array_merge(parent::toArray($request), [
            'worker_id' => $this->worker_id,
            'claimed_by' => $this->claimers(),
            'claimed_at' => optional($this->claimed_at)->toIso8601String(),
        ]);
    }
}
