<?php

declare(strict_types=1);

namespace App\Actions\Workers;

use App\Models\Worker;

/**
 * The result of provisioning a worker: the worker plus its freshly minted
 * plain-text token, which is only ever available at creation time.
 */
final readonly class WorkerCredentials
{
    public function __construct(
        public Worker $worker,
        public string $plainTextToken,
    ) {}
}
