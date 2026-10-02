<?php

declare(strict_types=1);

namespace App\ValueObjects;

/**
 * Normalized read-only evidence for one Gitea issue ready for an agent.
 */
final readonly class ReadyGiteaIssue
{
    /**
     * Create normalized issue evidence at the Gitea gateway boundary.
     *
     * @param  string  $repository  Canonical owner/name repository identifier.
     * @param  int  $number  Repository-local issue number.
     * @param  string  $title  Human-readable issue title.
     * @param  string  $url  Direct Gitea issue URL.
     */
    public function __construct(
        public string $repository,
        public int $number,
        public string $title,
        public string $url,
    ) {}

    /**
     * Return the tracker reference used by NightCrew jobs and fences.
     */
    public function reference(): string
    {
        return '#'.$this->number;
    }

    /**
     * Return a stable identity shared by every scan of this ticket.
     */
    public function sourceKey(): string
    {
        return 'gitea:'.$this->repository.$this->reference();
    }
}
