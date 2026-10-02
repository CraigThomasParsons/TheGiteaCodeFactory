<?php

declare(strict_types=1);

$readyRepositories = array_values(array_filter(array_map(
    'trim',
    explode(',', (string) env('NIGHT_CREW_READY_REPOSITORIES', '')),
)));

return [

    /*
    |--------------------------------------------------------------------------
    | Gitea fence
    |--------------------------------------------------------------------------
    |
    | The fence reflects a claim onto the tracker issue (assignee, status label,
    | comment) so humans and the crew hand work back and forth. It is optional
    | and best-effort: with no base_url + token configured it is inert, and a
    | Gitea outage never blocks a claim.
    |
    */

    'gitea' => [
        'base_url' => env('NIGHT_CREW_GITEA_URL', ''),
        'token' => env('NIGHT_CREW_GITEA_TOKEN', ''),

        // The account the crew assigns issues to. A dedicated bot account is
        // recommended so crew-held and human-held issues are distinguishable.
        'bot' => env('NIGHT_CREW_GITEA_BOT', 'night-crew-bot'),

        'timeout' => (int) env('NIGHT_CREW_GITEA_TIMEOUT', 5),

        'labels' => [
            'in_progress' => env('NIGHT_CREW_LABEL_IN_PROGRESS', 'status: in-progress'),
            'complete' => env('NIGHT_CREW_LABEL_COMPLETE', 'status: complete'),
        ],
    ],

    /*
    |--------------------------------------------------------------------------
    | Agent-ready issue intake
    |--------------------------------------------------------------------------
    |
    | This bounded scanner is an authenticated Intake caller. The stable source
    | identity makes repeated nightly scans safe while Gitea keeps its label.
    |
    */

    /*
    |--------------------------------------------------------------------------
    | Pull-request labelling
    |--------------------------------------------------------------------------
    |
    | The review/resolve/merge ticks are label-driven, but nothing applied the
    | first label. This sweep does, and grants review:automerge only to crew
    | scaffold work that already passed review.
    |
    */

    'pull_labelling' => [
        // '*' means every non-archived repository the token can see, resolved
        // fresh each run. Set NIGHT_CREW_PR_REPOS to a comma-separated list to
        // narrow it.
        'repositories' => array_values(array_filter(array_map('trim', explode(
            ',',
            (string) env('NIGHT_CREW_PR_REPOS', '*'),
        )))),
        'page_size' => (int) env('NIGHT_CREW_PR_PAGE_SIZE', 50),
        'page_limit' => (int) env('NIGHT_CREW_PR_PAGE_LIMIT', 10),

        // A crew PR must touch nothing outside these. Behaviour-bearing code is
        // deliberately absent: an automatic merge grant is for scaffolding,
        // documentation and tooling, never for product logic.
        'scaffold_paths' => array_values(array_filter(array_map('trim', explode(',', (string) env(
            'NIGHT_CREW_SCAFFOLD_PATHS',
            'scripts/,docs/,*.md,.gitignore,justfile,.slice-pipeline.toml',
        ))))),
    ],

    'ready_intake' => [
        'repositories' => $readyRepositories,
        'label' => env('NIGHT_CREW_READY_LABEL', 'ready-for-agent'),
        'page_size' => (int) env('NIGHT_CREW_READY_PAGE_SIZE', 100),
        'page_limit' => (int) env('NIGHT_CREW_READY_PAGE_LIMIT', 10),
    ],

];
