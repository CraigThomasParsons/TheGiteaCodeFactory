<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Actions\Jobs\IntakeReadyGiteaIssues;
use Illuminate\Http\JsonResponse;

/**
 * Authenticated HTTP door that asks Intake to scan configured Gitea sources.
 */
final class IntakeReadyGiteaIssuesController
{
    public function __construct(private IntakeReadyGiteaIssues $intake) {}

    /**
     * Run one bounded, idempotent ready-issue intake.
     */
    public function __invoke(): JsonResponse
    {
        return response()->json($this->intake->handle());
    }
}
