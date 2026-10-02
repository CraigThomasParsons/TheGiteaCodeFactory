<?php

declare(strict_types=1);

namespace App\Models;

use Database\Factories\WorkerFactory;
use Illuminate\Auth\Authenticatable as AuthenticatableTrait;
use Illuminate\Contracts\Auth\Authenticatable;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Laravel\Sanctum\HasApiTokens;

/**
 * One computer that runs night-crew work, authenticated by a Sanctum token.
 *
 * Implementing Authenticatable lets the Sanctum guard return a Worker as the
 * request user, so protected endpoints resolve straight to the calling machine.
 *
 * @property string $worker_id
 * @property array<int, string> $served_repos
 */
class Worker extends Model implements Authenticatable
{
    use AuthenticatableTrait;

    use HasApiTokens;

    /** @use HasFactory<WorkerFactory> */
    use HasFactory;

    /**
     * Mass-assignable attributes.
     *
     * @var list<string>
     */
    protected $fillable = [
        'worker_id',
        'served_repos',
    ];

    /**
     * Attribute casts.
     *
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'served_repos' => 'array',
        ];
    }

    /**
     * Determine whether this worker is able to run jobs for the given repo.
     *
     * @param  string  $repo  The repository identifier, e.g. "owner/Foo".
     */
    public function servesRepo(string $repo): bool
    {
        return in_array($repo, $this->served_repos, true);
    }
}
