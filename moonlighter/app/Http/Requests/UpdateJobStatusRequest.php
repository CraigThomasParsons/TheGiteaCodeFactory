<?php

declare(strict_types=1);

namespace App\Http\Requests;

use App\Enums\JobStatus;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

/**
 * Validate a worker's reported status change for a job.
 */
class UpdateJobStatusRequest extends FormRequest
{
    /**
     * Authorisation is handled by the auth:sanctum middleware on the route.
     */
    public function authorize(): bool
    {
        return true;
    }

    /**
     * The target status a worker may report. Whether it is legal from the job's
     * current status is decided by the transition action, not here.
     *
     * @return array<string, array<int, mixed>>
     */
    public function rules(): array
    {
        return [
            'status' => [
                'required',
                Rule::in([
                    JobStatus::Running->value,
                    JobStatus::Done->value,
                    JobStatus::Failed->value,
                    JobStatus::Queued->value,
                ]),
            ],
            'claim_token' => ['sometimes', 'uuid'],
            'receipt' => ['sometimes', 'array'],
        ];
    }
}
