<?php

declare(strict_types=1);

namespace App\Events;

use App\Models\NightCrewJob;
use Illuminate\Broadcasting\Channel;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

/**
 * A worker has claimed a job.
 */
final class JobClaimed implements ShouldBroadcast
{
    use Dispatchable;
    use InteractsWithSockets;
    use SerializesModels;

    public function __construct(public NightCrewJob $job) {}

    /**
     * The public channel the live dashboard listens on.
     */
    public function broadcastOn(): Channel
    {
        return new Channel('night-crew');
    }

    /**
     * The client-facing event name.
     */
    public function broadcastAs(): string
    {
        return 'job.claimed';
    }

    /**
     * The payload sent to subscribers.
     *
     * @return array<string, mixed>
     */
    public function broadcastWith(): array
    {
        return ['job' => $this->job->toBroadcastArray()];
    }
}
