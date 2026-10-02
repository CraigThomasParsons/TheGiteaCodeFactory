<?php

declare(strict_types=1);

namespace App\Http\Requests;

use App\Enums\JobKind;
use Illuminate\Contracts\Validation\Validator;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

/**
 * Validate a job submitted through the intake endpoint.
 *
 * Issue jobs must point at a tracker reference and carry no cadence; maintenance
 * jobs must carry a cadence, have no reference, and can never be contested.
 */
class StoreJobRequest extends FormRequest
{
    /**
     * Authorisation is handled by the auth:sanctum middleware on the route.
     */
    public function authorize(): bool
    {
        return true;
    }

    /**
     * Validation rules for an incoming job.
     *
     * @return array<string, array<int, mixed>>
     */
    public function rules(): array
    {
        return [
            'kind' => ['required', Rule::enum(JobKind::class)],
            'reference' => [
                'nullable', 'string', 'max:255',
                Rule::requiredIf($this->isIssue() || $this->isPullRequest()),
                Rule::prohibitedIf($this->isMaintenance()),
            ],
            'priority' => ['sometimes', 'integer', 'min:0'],
            'contested' => ['sometimes', 'boolean'],
            'cadence_minutes' => [
                'integer', 'min:1',
                Rule::requiredIf($this->isMaintenance()),
                Rule::prohibitedIf($this->isIssue() || $this->isPullRequest()),
            ],
            'payload' => ['nullable', 'array'],
            'payload.head' => [Rule::requiredIf($this->isPullRequest()), 'string', 'regex:/^[a-f0-9]{40}$/'],
            'payload.base' => [Rule::requiredIf($this->isPullRequest()), 'string', 'regex:/^[a-f0-9]{40}$/'],
            'payload.stage' => [Rule::requiredIf($this->isPullRequest()), Rule::in(['review', 'resolve', 'arbitrate', 'post_merge'])],
            'payload.attempt' => [Rule::requiredIf($this->isPullRequest()), 'integer', 'min:0', 'max:100'],
        ];
    }

    /**
     * Cross-field checks that do not fit a single-field rule.
     *
     * @return array<int, callable>
     */
    public function after(): array
    {
        return [
            function (Validator $validator): void {
                // A maintenance job has no tracker ticket to race, so contesting
                // it is meaningless and is rejected outright.
                if (($this->isMaintenance() || $this->isPullRequest()) && $this->boolean('contested')) {
                    $validator->errors()->add('contested', 'Maintenance jobs cannot be contested.');
                }
            },
        ];
    }

    /**
     * Whether the submitted job is an issue job.
     */
    private function isIssue(): bool
    {
        return $this->input('kind') === JobKind::Issue->value;
    }

    /**
     * Whether the submitted job is a maintenance job.
     */
    private function isMaintenance(): bool
    {
        return $this->input('kind') === JobKind::Maintenance->value;
    }

    /** Whether this submission describes one immutable PR stage. */
    private function isPullRequest(): bool
    {
        return $this->input('kind') === JobKind::PullRequest->value;
    }
}
