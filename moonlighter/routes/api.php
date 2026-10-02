<?php

declare(strict_types=1);

use App\Http\Controllers\Api\ClaimNextController;
use App\Http\Controllers\Api\IntakeReadyGiteaIssuesController;
use App\Http\Controllers\Api\ListHeldJobsController;
use App\Http\Controllers\Api\ListPrJobsController;
use App\Http\Controllers\Api\StoreJobController;
use App\Http\Controllers\Api\UpdateJobStatusController;
use App\Http\Controllers\Api\WorkerIdentityController;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;

Route::get('/user', function (Request $request) {
    return $request->user();
})->middleware('auth:sanctum');

Route::middleware('auth:sanctum')->group(function () {
    Route::get('/pr-jobs', ListPrJobsController::class);
    // A worker's identity probe: confirms its token works and reports the repos
    // it is allowed to run.
    Route::get('/worker/me', WorkerIdentityController::class);

    // Read-only reconciliation: the jobs this worker currently holds, so a
    // restarted client can match its ledger without claiming anything new.
    Route::get('/worker/jobs', ListHeldJobsController::class);

    // The single intake door. {repo} is an owner/name pair, so it is allowed to
    // contain a slash; the trailing /jobs still anchors the match.
    Route::post('/repos/{repo}/jobs', StoreJobController::class)
        ->where('repo', '[A-Za-z0-9._/-]+');

    // A bounded Gitea scan is also a Caller and therefore enters through an
    // authenticated Intake route rather than writing coordinator state directly.
    Route::post('/intake/gitea-ready', IntakeReadyGiteaIssuesController::class);

    // The atomic claim: a worker pulls its next actionable job.
    Route::post('/claim-next', ClaimNextController::class);

    // A worker reports progress: claimed -> running -> done|failed.
    Route::patch('/jobs/{job}/status', UpdateJobStatusController::class);
});
