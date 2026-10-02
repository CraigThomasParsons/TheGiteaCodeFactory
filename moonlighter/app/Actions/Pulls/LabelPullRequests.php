<?php

declare(strict_types=1);

namespace App\Actions\Pulls;

use App\Services\Gitea\GiteaPullRequestGateway;
use Throwable;

/**
 * Keep every open pull request's review label truthful.
 *
 * The review, resolve and merge ticks are all label-driven, but nothing put the
 * first label on. A PR opened without `review:requested` sat untouched forever,
 * and a PR whose head moved after a review kept a `review:clear` that described
 * a commit nobody had looked at any more. This action is that missing step, and
 * only that step: it never reviews, never resolves and never merges.
 */
final class LabelPullRequests
{
    public const REQUESTED = 'review:requested';

    public const AUTOMERGE = 'review:automerge';

    /** A clean review of the current head: the factory's merge gate requires it. */
    public const CLEAR = 'review:clear';

    /** The older name for CLEAR, still written by earlier review skills. */
    public const LEGACY_CLEAN = 'review:clean';

    /** Labels that mean the review found nothing to fix. */
    private const CLEAN_VERDICTS = [self::CLEAR, self::LEGACY_CLEAN];

    /** Labels that describe a completed review of one specific head. */
    private const REVIEW_VERDICTS = [self::CLEAR, self::LEGACY_CLEAN, 'review:findings', 'review:resolved'];

    /** Any of these means a human owns the PR; the bot keeps its hands off. */
    private const HANDS_OFF = ['review:needs-human', 'night:hold', 'review:in-progress', 'review:resolving', 'review:merging'];

    public function __construct(private GiteaPullRequestGateway $gateway) {}

    /**
     * @param  bool  $dryRun
     *
     * @return array{labelled: int, refreshed: int, granted: int, skipped: int, repositories: array<string, mixed>}
     */
    public function handle(bool $dryRun = false): array
    {
        $result = ['labelled' => 0, 'refreshed' => 0, 'granted' => 0, 'skipped' => 0, 'repositories' => []];

        foreach ($this->gateway->pipelineRepositories() as $repository) {
            try {
                $result['repositories'][$repository] = $this->sweep($repository, $dryRun, $result);
            } catch (Throwable $exception) {
                // One unreachable repository must not hide the rest.
                $result['repositories'][$repository] = [
                    'available' => false,
                    'error' => $exception->getMessage(),
                ];
            }
        }

        return $result;
    }

    /**
     * @param  array<string, mixed>  $result
     * @param  string  $repository
     * @param  bool  $dryRun
     *
     * @return array<string, mixed>
     */
    private function sweep(string $repository, bool $dryRun, array &$result): array
    {
        $pulls = $this->gateway->openPullRequests($repository);
        $labelIds = $dryRun ? [] : $this->gateway->labelIds($repository);
        $actions = [];

        foreach ($pulls as $pull) {
            $action = $this->decide($repository, $pull);

            if ($action === null) {
                continue;
            }

            // A label the repository does not define cannot be posted. Record
            // that as evidence instead of counting work that never happened.
            $missing = $dryRun ? [] : array_values(array_diff($action['add'], array_keys($labelIds)));

            if ($missing !== []) {
                $actions[] = array_replace(['pr' => $pull['number']] + $action, [
                    'kind' => 'skipped',
                    'why' => 'repository has no label '.implode(', ', $missing),
                ]);
                $result['skipped']++;

                continue;
            }

            $actions[] = ['pr' => $pull['number']] + $action;
            $result[$action['kind']]++;

            if (! $dryRun) {
                $this->apply($repository, (int) $pull['number'], $action, $labelIds);
            }
        }

        return ['available' => true, 'open' => count($pulls), 'actions' => $actions];
    }

    /**
     * Decide the single label change this pull request needs, if any.
     *
     * @param  array<string, mixed>  $pull
     * @param  string  $repository
     *
     * @return array{kind: string, add: list<string>, remove: list<string>, why: string}|null
     */
    private function decide(string $repository, array $pull): ?array
    {
        $labels = (array) $pull['labels'];

        if ($pull['draft'] === true) {
            return null;
        }

        if ($this->isBot((string) $pull['author'])) {
            return null;
        }

        if (array_intersect($labels, self::HANDS_OFF) !== []) {
            return null;
        }

        $verdicts = array_values(array_intersect($labels, self::REVIEW_VERDICTS));

        // A verdict describes one commit. When the head moves past the commit
        // the review actually read, the label is no longer a statement about
        // this pull request: it is a statement about a commit that is no longer
        // the tip. Strip it and ask for a fresh review.
        //
        // This runs BEFORE the automerge grant on purpose. A stale review:clear
        // must never earn merge authority; the merge tick would refuse it on its
        // own marker check, but a label that says "clean" about unread code is
        // wrong on the pull request page long before anything tries to merge it.
        if ($verdicts !== [] && $this->headMovedPastReview($repository, $pull)) {
            return [
                'kind' => 'refreshed',
                'add' => [self::REQUESTED],
                'remove' => array_values(array_merge($verdicts, [self::AUTOMERGE])),
                'why' => 'head moved past the reviewed commit',
            ];
        }

        // Grant merge authority only to crew-produced scaffold work that has
        // already passed review. This is the one place the bot hands out an
        // authority rather than describing a state, so both gates are required.
        if (array_intersect($labels, self::CLEAN_VERDICTS) !== [] && ! in_array(self::AUTOMERGE, $labels, true)) {
            if ($this->isCrewScaffoldWork($repository, $pull)) {
                return [
                    'kind' => 'granted',
                    'add' => [self::AUTOMERGE],
                    'remove' => [],
                    'why' => 'clean review on crew scaffold work',
                ];
            }

            return null;
        }

        if ($verdicts === [] && ! in_array(self::REQUESTED, $labels, true)) {
            return [
                'kind' => 'labelled',
                'add' => [self::REQUESTED],
                'remove' => [],
                'why' => 'open, unlabelled, awaiting first review',
            ];
        }

        return null;
    }

    /**
     * Has this pull request moved past the commit its review actually read?
     *
     * Unmarked is treated as NOT moved. An older review that predates markers,
     * or a verdict a human applied by hand, is left alone rather than being
     * stripped on the strength of a missing marker.
     *
     * @param  string  $repository  Canonical owner/name repository identifier.
     * @param  array<string, mixed>  $pull  One normalised pull request.
     *
     * @return bool True when the reviewed commit is not the current head.
     */
    private function headMovedPastReview(string $repository, array $pull): bool
    {
        $reviewed = $this->gateway->reviewedHead($repository, (int) $pull['number']);

        if ($reviewed === null) {
            return false;
        }

        return $reviewed !== (string) $pull['head_sha'];
    }

    /**
     * Crew work is identified by branch shape, not by author: the night-shift
     * launcher authenticates as the repository owner, so the author field
     * cannot distinguish an agent's PR from a human's. Every launcher branch is
     * feature/<issue-number>-<slug>.
     *
     * @param  array<string, mixed>  $pull
     * @param  string  $repository
     *
     * @return bool
     */
    private function isCrewScaffoldWork(string $repository, array $pull): bool
    {
        if (preg_match('#^feature/\d+-#', (string) $pull['head_ref']) !== 1) {
            return false;
        }

        $allowed = (array) config('nightcrew.pull_labelling.scaffold_paths');
        $paths = $this->gateway->changedPaths($repository, (int) $pull['number']);

        if ($paths === []) {
            return false;
        }

        foreach ($paths as $path) {
            if (! $this->isScaffoldPath($path, $allowed)) {
                return false;
            }
        }

        return true;
    }

    /**
     * Whether one changed path falls inside the configured scaffold entries.
     *
     * Only entries ending in '/' are directory prefixes. Every other entry is
     * a file name or glob matched against the whole path, so `justfile` admits
     * `justfile` but not `justfile.d/anything.php`.
     *
     * @param  string  $path
     * @param  array<int, mixed>  $allowed
     *
     * @return bool
     */
    private function isScaffoldPath(string $path, array $allowed): bool
    {
        foreach ($allowed as $entry) {
            $entry = (string) $entry;

            $matches = str_ends_with($entry, '/')
                ? str_starts_with($path, $entry)
                : fnmatch($entry, $path);

            if ($matches) {
                return true;
            }
        }

        return false;
    }

    /**
     * @param  array{kind: string, add: list<string>, remove: list<string>, why: string}  $action
     * @param  array<string, int>  $labelIds
     * @param  string  $repository
     * @param  int  $number
     *
     * @return void
     */
    private function apply(string $repository, int $number, array $action, array $labelIds): void
    {
        foreach ($action['remove'] as $name) {
            if (isset($labelIds[$name])) {
                $this->gateway->removeLabel($repository, $number, $labelIds[$name]);
            }
        }

        $add = [];

        foreach ($action['add'] as $name) {
            if (isset($labelIds[$name])) {
                $add[] = $labelIds[$name];
            }
        }

        $this->gateway->addLabels($repository, $number, $add);
    }

    /**
     * Bot accounts never get a review requested on their behalf.
     *
     * @param  string  $login
     *
     * @return bool
     */
    private function isBot(string $login): bool
    {
        $login = strtolower($login);

        return str_ends_with($login, '[bot]') || in_array($login, ['gitea-actions', 'actions-user'], true);
    }
}
