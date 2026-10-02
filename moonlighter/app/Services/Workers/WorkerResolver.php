<?php

declare(strict_types=1);

namespace App\Services\Workers;

use App\Models\Worker;
use Illuminate\Auth\Access\AuthorizationException;
use Illuminate\Http\Request;

/**
 * Resolve the authenticated request back to the Worker that owns its token.
 *
 * Both workers and ordinary users can hold Sanctum tokens, so worker-only
 * endpoints use this to insist the caller really is a worker before proceeding.
 */
final class WorkerResolver
{
    /**
     * Return the Worker behind the request's token, or reject the request when
     * the authenticated identity is not a worker.
     *
     * @param  Request  $request
     *
     * @throws AuthorizationException When the token does not belong to a worker.
     */
    public function resolve(Request $request): Worker
    {
        $authenticated = $request->user();

        // Guard: a non-worker token (for example a human user's) must not reach
        // worker endpoints, even though it authenticated successfully.
        if (! $authenticated instanceof Worker) {
            throw new AuthorizationException('The authenticated token does not belong to a worker.');
        }

        return $authenticated;
    }
}
