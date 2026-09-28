#!/usr/bin/env node

/**
 * Portable advisory PR reviewer.
 *
 * Runs from a trusted checkout, scans the PR diff for secret-like content,
 * asks a chain of LLM providers (Gemini, then Groq, then a local Ollama
 * server) for a style review with per-provider retry and backoff, and posts a
 * structured Gitea review marker that local Night Shift remediation can
 * consume later.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const EXIT_CODE_SUCCESS = 0;
const EXIT_CODE_ERROR = 1;
const RADIX_DECIMAL = 10;
const EMPTY_LENGTH = 0;
const COMMAND_SUCCESS_STATUS = 0;
const HTTP_OK_MINIMUM = 200;
const HTTP_OK_MAXIMUM_EXCLUSIVE = 300;
const FIRST_ARRAY_INDEX = 0;
const SECOND_ARRAY_INDEX = 1;
const THIRD_ARRAY_INDEX = 2;
const REVIEW_MARKER_PREFIX = "<!-- night-shift-review-task:v1 ";
const REVIEW_MARKER_SUFFIX = " -->";
const VALIDATION_PROFILE = "pr-review";
const DEFAULT_LOOP_MAX_ATTEMPTS = 3;
const SECRET_CONTEXT_LIMIT = 160;
// A structural pattern match is only treated as a secret when the captured
// candidate's Shannon entropy reaches this bits/char threshold. Calibrated:
// readable identifiers (SCREAMING_SNAKE_CASE constants, enum keys) measure
// ~3.1-3.4; real random tokens measure ~3.9-4.3; 3.5 cleanly separates them.
const SECRET_MIN_ENTROPY_BITS = 3.5;
const HTTP_TOO_MANY_REQUESTS = 429;
const HTTP_SERVER_ERROR_MINIMUM = 500;
const DEFAULT_PROVIDER_RETRY_ATTEMPTS = 3;
// Backoff schedule (ms) applied between retryable provider failures: 2s, 8s, 20s.
const RETRY_BACKOFF_MS = [2000, 8000, 20000];
const PROVIDER_TEMPERATURE = 0.2;
const NOT_FOUND_INDEX = -1;

const GITEA_TOKEN = process.env.GITEA_TOKEN || "";
const GITEA_API_URL = process.env.GITEA_API_URL || "";
const GITEA_REPOSITORY = process.env.GITEA_REPOSITORY || "";
const PR_NUMBER_RAW = process.env.PR_NUMBER || "";
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || "";
// Model is overridable so a quota/availability change never needs a code edit.
// gemini-2.0-flash has zero free-tier quota on the configured key; 2.5-flash works.
const GEMINI_MODEL = process.env.GEMINI_MODEL || "gemini-2.5-flash";
const BASE_BRANCH = process.env.BASE_BRANCH || "develop";
const HEAD_BRANCH = process.env.HEAD_BRANCH || "";
const PR_REVIEW_LOOP_MAX_ATTEMPTS = Number.parseInt(
    process.env.PR_REVIEW_LOOP_MAX_ATTEMPTS || String(DEFAULT_LOOP_MAX_ATTEMPTS),
    RADIX_DECIMAL,
);

// mammouth.ai (paid, OpenAI-compatible, frontier models) is the preferred
// fallback after free Gemini; only joins the chain when its key is set.
const MAMMOUTH_API_KEY = process.env.MAMMOUTH_API_KEY || "";
const MAMMOUTH_MODEL = process.env.MAMMOUTH_MODEL || "claude-sonnet-4-6";
const MAMMOUTH_BASE_URL = process.env.MAMMOUTH_BASE_URL || "https://api.mammouth.ai/v1";
// Groq is the fast free cloud fallback; only joins the chain when its key is set.
const GROQ_API_KEY = process.env.GROQ_API_KEY || "";
const GROQ_MODEL = process.env.GROQ_MODEL || "llama-3.3-70b-versatile";
const GROQ_BASE_URL = process.env.GROQ_BASE_URL || "https://api.groq.com/openai/v1";
// Ollama is the no-quota local anchor; only joins the chain when a URL is set.
const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL || "";
const OLLAMA_MODEL = process.env.OLLAMA_MODEL || "qwen2.5-coder:7b";
const OLLAMA_API_KEY = process.env.OLLAMA_API_KEY || "";
const PROVIDER_RETRY_ATTEMPTS = Number.parseInt(
    process.env.PROVIDER_RETRY_ATTEMPTS || String(DEFAULT_PROVIDER_RETRY_ATTEMPTS),
    RADIX_DECIMAL,
);

const JS_STYLE_PATH = process.env.REVIEW_JS_STYLE_PATH || "docs/style/javascript_node_style.md";
const TS_STYLE_PATH = process.env.REVIEW_TS_STYLE_PATH || "docs/style/ts_node_style.md";

// Each pattern carries an `entropyGated` flag and the capture group holding the
// candidate string. Token-shaped patterns are entropy-gated so readable
// identifiers (e.g. the constant GITEA_REVIEW_EVENT_BY_VERDICT) are not flagged
// as leaked tokens; the structural private-key marker is always a real secret.
const SECRET_PATTERNS = [
    {
        name: "private-key",
        pattern: /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
        entropyGated: false,
        candidateGroup: FIRST_ARRAY_INDEX,
    },
    {
        name: "generic-token-assignment",
        pattern: /\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['"]([^'"]{12,})['"]/i,
        entropyGated: true,
        candidateGroup: THIRD_ARRAY_INDEX,
    },
    {
        name: "bearer-token",
        pattern: /\bBearer\s+([A-Za-z0-9._~+/=-]{20,})/,
        entropyGated: true,
        candidateGroup: SECOND_ARRAY_INDEX,
    },
    {
        // Case-SENSITIVE lowercase prefix and NO underscores in the body, so
        // SCREAMING_SNAKE_CASE identifiers no longer match structurally; the
        // body is then entropy-gated as a second line of defence.
        name: "github-or-gitea-token",
        pattern: /\b(ghp|gho|ghu|ghs|gitea)_([A-Za-z0-9]{20,})/,
        entropyGated: true,
        candidateGroup: THIRD_ARRAY_INDEX,
    },
];

const VALID_VERDICTS = ["APPROVE", "REQUEST_CHANGES", "COMMENT"];

// Gitea's review event enum is ["APPROVED", "PENDING", "COMMENT",
// "REQUEST_CHANGES", "REQUEST_REVIEW"] — note "APPROVED", not "APPROVE".
// Submitting the LLM's "APPROVE" verdict verbatim is an unrecognized event, so
// Gitea leaves the review as an invisible PENDING draft. Map verdict -> event.
const GITEA_REVIEW_EVENT_BY_VERDICT = {
    APPROVE: "APPROVED",
    REQUEST_CHANGES: "REQUEST_CHANGES",
    COMMENT: "COMMENT",
};

/**
 * Run a command without invoking a shell.
 *
 * @param {string} commandName Executable name.
 * @param {string[]} commandArguments Arguments passed to the executable.
 * @returns {string} Trimmed stdout.
 */
function runCommand(commandName, commandArguments) {
    const commandResult = spawnSync(commandName, commandArguments, {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
    });

    // Fail fast so the workflow never reviews an unknown diff.
    if (commandResult.status !== COMMAND_SUCCESS_STATUS) {
        throw new Error(`Command failed: ${commandName} ${commandArguments.join(" ")}\n${commandResult.stderr}`);
    }

    return commandResult.stdout.trim();
}

/**
 * Return whether an HTTP status code is successful.
 *
 * @param {number} statusCode HTTP response status.
 * @returns {boolean} True for 2xx statuses.
 */
function isSuccessfulStatus(statusCode) {
    return statusCode >= HTTP_OK_MINIMUM && statusCode < HTTP_OK_MAXIMUM_EXCLUSIVE;
}

/**
 * Fetch the raw PR diff from the Gitea API.
 *
 * @param {number} prNumber Gitea pull request number.
 * @returns {Promise<string>} Raw PR diff.
 */
async function fetchPullRequestDiff(prNumber) {
    const cleanApiUrl = GITEA_API_URL.replace(/\/$/, "");
    const diffUrl = `${cleanApiUrl}/repos/${GITEA_REPOSITORY}/pulls/${prNumber}.diff`;

    console.log(`Fetching PR diff from: ${diffUrl}`);

    try {
        const response = await fetch(diffUrl, {
            headers: {
                Authorization: `token ${GITEA_TOKEN}`,
                Accept: "text/plain",
            },
        });

        if (response.ok) {
            return await response.text();
        }

        console.warn(`Gitea diff fetch returned HTTP ${response.status}; refusing to review an unknown diff.`);
    } catch (apiError) {
        console.warn(`Gitea diff fetch failed: ${apiError.message}; refusing to review an unknown diff.`);
    }

    throw new Error("Cannot fetch the PR diff; refusing a local-checkout fallback.");
}

/**
 * Read a style guide from the trusted checkout.
 *
 * @param {string} filePath Relative style-guide path.
 * @returns {string} Style-guide markdown or an empty string when absent.
 */
function readStyleGuide(filePath) {
    const resolvedPath = path.resolve(filePath);

    // Missing style docs should be visible but not block API review plumbing.
    if (!fs.existsSync(resolvedPath)) {
        console.warn(`Style guide not found: ${resolvedPath}`);

        return "";
    }

    return fs.readFileSync(resolvedPath, "utf8");
}

/**
 * Extract only added diff lines for pre-Gemini secret scanning.
 *
 * @param {string} diffContent Raw PR diff.
 * @returns {string[]} Added lines without diff metadata.
 */
function extractAddedDiffLines(diffContent) {
    const addedLines = [];

    for (const diffLine of diffContent.split("\n")) {
        if (!diffLine.startsWith("+")) {
            continue;
        }

        if (diffLine.startsWith("+++")) {
            continue;
        }

        addedLines.push(diffLine.slice(SECOND_ARRAY_INDEX - FIRST_ARRAY_INDEX));
    }

    return addedLines;
}

/**
 * Shannon entropy of a string in bits per character.
 *
 * @param {string} text Candidate string.
 * @returns {number} Entropy in bits/char (0 for empty input).
 */
export function shannonEntropyBitsPerChar(text) {
    if (text.length === EMPTY_LENGTH) {
        return EMPTY_LENGTH;
    }

    const characterCounts = new Map();

    for (const character of text) {
        const previousCount = characterCounts.get(character) || EMPTY_LENGTH;
        characterCounts.set(character, previousCount + SECOND_ARRAY_INDEX);
    }

    let entropy = EMPTY_LENGTH;

    for (const count of characterCounts.values()) {
        const probability = count / text.length;
        entropy -= probability * Math.log2(probability);
    }

    return entropy;
}

/**
 * Whether a captured candidate looks like a real high-entropy secret rather
 * than a readable identifier (e.g. a SCREAMING_SNAKE_CASE constant).
 *
 * @param {string} candidate Captured candidate string.
 * @returns {boolean} True when entropy meets the secret threshold.
 */
export function looksLikeHighEntropySecret(candidate) {
    return shannonEntropyBitsPerChar(candidate) >= SECRET_MIN_ENTROPY_BITS;
}

/**
 * Find secret-like content in added diff lines.
 *
 * @param {string} diffContent Raw PR diff.
 * @returns {Array<{pattern: string, line: string}>} Secret findings.
 */
export function findSecretLikeContent(diffContent) {
    const findings = [];

    for (const addedLine of extractAddedDiffLines(diffContent)) {
        for (const secretPattern of SECRET_PATTERNS) {
            const match = secretPattern.pattern.exec(addedLine);

            // Guard: no structural match means this pattern is not a candidate.
            if (match === null) {
                continue;
            }

            // Entropy gate: a token-shaped match is only a finding when the
            // captured string is high-entropy. This is what stops readable
            // identifiers from being flagged as leaked tokens.
            if (secretPattern.entropyGated) {
                const candidate = match[secretPattern.candidateGroup];

                if (typeof candidate !== "string" || !looksLikeHighEntropySecret(candidate)) {
                    continue;
                }
            }

            findings.push({
                pattern: secretPattern.name,
                line: addedLine.slice(EMPTY_LENGTH, SECRET_CONTEXT_LIMIT),
            });
        }
    }

    return findings;
}

/**
 * Build the shared reviewer prompt sent to every provider.
 *
 * @param {string} diffContent Raw PR diff.
 * @param {string} jsStyle JavaScript style guide.
 * @param {string} tsStyle TypeScript style guide.
 * @returns {string} Prompt instructions including the diff.
 */
export function buildReviewPrompt(diffContent, jsStyle, tsStyle) {
    return `You are an automated code reviewer for the ${GITEA_REPOSITORY || "target"} repository.
Review only the added and changed lines in the diff.

=== JavaScript / Node Style Guide ===
${jsStyle}

=== TypeScript Style Guide ===
${tsStyle}

Check for:
- 4-space indentation.
- No single-letter variable names.
- JSDoc on newly added functions with @param and @returns.
- Magic numbers extracted to UPPER_SNAKE_CASE constants.
- No ternary operators.
- Clear fail-fast error handling with commented guard clauses.

Return ONLY a JSON object with exactly these keys:
- "verdict": one of "APPROVE", "REQUEST_CHANGES", or "COMMENT".
- "review": a markdown string containing the review.

=== Pull Request Diff ===
\`\`\`diff
${diffContent}
\`\`\``;
}

/**
 * Build an Error flagged as retryable so the backoff loop will retry it.
 *
 * @param {string} message Human-readable failure description.
 * @returns {Error} Error carrying a retryable flag.
 */
function makeRetryableError(message) {
    const retryableError = new Error(message);
    retryableError.retryable = true;

    return retryableError;
}

/**
 * Return whether an HTTP status is a transient failure worth retrying.
 *
 * @param {number} statusCode HTTP response status.
 * @returns {boolean} True for 429 and 5xx statuses.
 */
export function isRetryableStatus(statusCode) {
    // 429 (overload) and 5xx (server-side) are transient; 4xx caller errors are not.
    if (statusCode === HTTP_TOO_MANY_REQUESTS) {
        return true;
    }

    return statusCode >= HTTP_SERVER_ERROR_MINIMUM;
}

/**
 * Pause execution for a fixed number of milliseconds.
 *
 * @param {number} milliseconds Delay duration.
 * @returns {Promise<void>} Resolves after the delay.
 */
function sleep(milliseconds) {
    return new Promise((resolve) => {
        setTimeout(resolve, milliseconds);
    });
}

/**
 * Run an async attempt with exponential backoff on retryable failures.
 *
 * @param {string} providerLabel Provider name used in log output.
 * @param {() => Promise<{verdict: string, review: string}>} attemptFunction Single review attempt.
 * @returns {Promise<{verdict: string, review: string}>} The first successful review.
 */
export async function withRetries(providerLabel, attemptFunction) {
    let lastError;

    for (let attemptIndex = FIRST_ARRAY_INDEX; attemptIndex < PROVIDER_RETRY_ATTEMPTS; attemptIndex += SECOND_ARRAY_INDEX) {
        try {
            return await attemptFunction();
        } catch (attemptError) {
            lastError = attemptError;

            const isLastAttempt = attemptIndex >= PROVIDER_RETRY_ATTEMPTS - SECOND_ARRAY_INDEX;

            // Stop immediately on non-transient errors or once attempts are exhausted.
            if (attemptError.retryable !== true || isLastAttempt) {
                break;
            }

            const backoffIndex = Math.min(attemptIndex, RETRY_BACKOFF_MS.length - SECOND_ARRAY_INDEX);
            const backoffMilliseconds = RETRY_BACKOFF_MS[backoffIndex];

            console.warn(`${providerLabel} attempt ${attemptIndex + SECOND_ARRAY_INDEX} failed (${attemptError.message}); retrying in ${backoffMilliseconds}ms.`);

            await sleep(backoffMilliseconds);
        }
    }

    throw lastError;
}

/**
 * Parse a JSON object from model text, tolerating markdown code fences.
 *
 * @param {string} rawText Model response text.
 * @returns {unknown} Parsed JSON value.
 */
export function parseJsonObject(rawText) {
    // Some models wrap JSON in ```json fences, sometimes with surrounding
    // whitespace; trim first so the anchored fence-strip still matches.
    const withoutFences = rawText
        .trim()
        .replace(/^```(?:json)?\s*/i, "")
        .replace(/\s*```$/i, "")
        .trim();

    try {
        return JSON.parse(withoutFences);
    } catch (directParseError) {
        // Fallback: a model (mammouth without response_format) may add prose
        // around the object, so extract the outermost {...} and parse that.
        const firstBrace = withoutFences.indexOf("{");
        const lastBrace = withoutFences.lastIndexOf("}");

        // Guard: no plausible object span means the response was genuinely bad.
        if (firstBrace === NOT_FOUND_INDEX || lastBrace <= firstBrace) {
            throw directParseError;
        }

        return JSON.parse(withoutFences.slice(firstBrace, lastBrace + SECOND_ARRAY_INDEX));
    }
}

/**
 * Request a review from the native Gemini API (single attempt).
 *
 * @param {string} reviewPrompt Shared reviewer prompt.
 * @returns {Promise<{verdict: string, review: string}>} Validated review payload.
 */
async function reviewWithGemini(reviewPrompt) {
    const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_API_KEY}`;
    const requestPayload = {
        contents: [
            {
                parts: [
                    {
                        text: reviewPrompt,
                    },
                ],
            },
        ],
        generationConfig: {
            responseMimeType: "application/json",
            responseSchema: {
                type: "OBJECT",
                properties: {
                    verdict: {
                        type: "STRING",
                        enum: VALID_VERDICTS,
                    },
                    review: {
                        type: "STRING",
                    },
                },
                required: ["verdict", "review"],
            },
        },
    };

    let response;

    try {
        response = await fetch(endpoint, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(requestPayload),
        });
    } catch (networkError) {
        // Network failures are transient from our side; let the backoff retry them.
        throw makeRetryableError(`Gemini request failed: ${networkError.message}`);
    }

    const responseData = await response.json();

    // Guard: surface API failures, flagging transient ones (429/5xx) for retry.
    if (!isSuccessfulStatus(response.status)) {
        const apiError = new Error(`Gemini API returned HTTP ${response.status}: ${JSON.stringify(responseData)}`);
        apiError.retryable = isRetryableStatus(response.status);

        throw apiError;
    }

    const rawText = responseData.candidates?.[FIRST_ARRAY_INDEX]?.content?.parts?.[FIRST_ARRAY_INDEX]?.text;

    // Guard: the schema promise is external, so validate the returned shape locally.
    if (typeof rawText !== "string" || rawText.trim() === "") {
        throw new Error("Gemini response did not contain review text.");
    }

    return validateReviewPayload(JSON.parse(rawText));
}

/**
 * Request a review from any OpenAI-compatible chat endpoint (single attempt).
 *
 * @param {string} reviewPrompt Shared reviewer prompt.
 * @param {string} baseUrl OpenAI-compatible base URL ending in /v1.
 * @param {string} apiKey Bearer token, or an empty string for keyless local servers.
 * @param {string} modelName Model identifier.
 * @param {string} providerLabel Provider name used in errors and logs.
 * @param {boolean} supportsJsonResponseFormat Whether to send response_format.
 * @returns {Promise<{verdict: string, review: string}>} Validated review payload.
 */
async function reviewWithOpenAiCompatible(reviewPrompt, baseUrl, apiKey, modelName, providerLabel, supportsJsonResponseFormat) {
    const cleanBaseUrl = baseUrl.replace(/\/$/, "");
    const endpoint = `${cleanBaseUrl}/chat/completions`;
    const requestHeaders = {
        "Content-Type": "application/json",
    };

    // Local servers (Ollama) accept keyless requests; cloud providers need a Bearer token.
    if (apiKey !== "") {
        requestHeaders.Authorization = `Bearer ${apiKey}`;
    }

    const requestPayload = {
        model: modelName,
        messages: [
            {
                role: "user",
                content: reviewPrompt,
            },
        ],
        temperature: PROVIDER_TEMPERATURE,
    };

    // Not every OpenAI-compatible provider accepts response_format (mammouth
    // does not); enable it only where supported and otherwise rely on the
    // prompt plus the tolerant JSON parser.
    if (supportsJsonResponseFormat) {
        requestPayload.response_format = {
            type: "json_object",
        };
    }

    let response;

    try {
        response = await fetch(endpoint, {
            method: "POST",
            headers: requestHeaders,
            body: JSON.stringify(requestPayload),
        });
    } catch (networkError) {
        // A sleeping local model or a cloud blip is transient; allow retry.
        throw makeRetryableError(`${providerLabel} request failed: ${networkError.message}`);
    }

    const responseData = await response.json();

    // Guard: surface API failures, flagging transient ones (429/5xx) for retry.
    if (!isSuccessfulStatus(response.status)) {
        const apiError = new Error(`${providerLabel} API returned HTTP ${response.status}: ${JSON.stringify(responseData)}`);
        apiError.retryable = isRetryableStatus(response.status);

        throw apiError;
    }

    const rawText = responseData.choices?.[FIRST_ARRAY_INDEX]?.message?.content;

    // Guard: validate the returned shape before trusting it.
    if (typeof rawText !== "string" || rawText.trim() === "") {
        throw new Error(`${providerLabel} response did not contain review text.`);
    }

    return validateReviewPayload(parseJsonObject(rawText));
}

/**
 * Request a review from Groq (single attempt).
 *
 * @param {string} reviewPrompt Shared reviewer prompt.
 * @returns {Promise<{verdict: string, review: string}>} Validated review payload.
 */
async function reviewWithGroq(reviewPrompt) {
    return reviewWithOpenAiCompatible(reviewPrompt, GROQ_BASE_URL, GROQ_API_KEY, GROQ_MODEL, "Groq", true);
}

/**
 * Request a review from mammouth.ai (single attempt).
 *
 * @param {string} reviewPrompt Shared reviewer prompt.
 * @returns {Promise<{verdict: string, review: string}>} Validated review payload.
 */
async function reviewWithMammouth(reviewPrompt) {
    // mammouth does not document response_format, so request JSON via the
    // prompt and lean on the tolerant parser (supportsJsonResponseFormat=false).
    return reviewWithOpenAiCompatible(reviewPrompt, MAMMOUTH_BASE_URL, MAMMOUTH_API_KEY, MAMMOUTH_MODEL, "mammouth", false);
}

/**
 * Request a review from a local Ollama server (single attempt).
 *
 * @param {string} reviewPrompt Shared reviewer prompt.
 * @returns {Promise<{verdict: string, review: string}>} Validated review payload.
 */
async function reviewWithOllama(reviewPrompt) {
    return reviewWithOpenAiCompatible(reviewPrompt, OLLAMA_BASE_URL, OLLAMA_API_KEY, OLLAMA_MODEL, "Ollama", true);
}

/**
 * Build the ordered provider chain from whatever is configured.
 *
 * @returns {Array<{label: string, run: (reviewPrompt: string) => Promise<{verdict: string, review: string}>}>} Providers to try in order.
 */
function buildProviderChain() {
    const providers = [];

    // Gemini stays primary; only included when a key is present.
    if (GEMINI_API_KEY !== "") {
        providers.push({ label: `Gemini (${GEMINI_MODEL})`, run: reviewWithGemini });
    }

    // mammouth (paid, frontier models) is the preferred fallback after Gemini.
    if (MAMMOUTH_API_KEY !== "") {
        providers.push({ label: `mammouth (${MAMMOUTH_MODEL})`, run: reviewWithMammouth });
    }

    // Groq is the fast free cloud fallback when its key is configured.
    if (GROQ_API_KEY !== "") {
        providers.push({ label: `Groq (${GROQ_MODEL})`, run: reviewWithGroq });
    }

    // Ollama is the no-quota local anchor; only included when a base URL is set.
    if (OLLAMA_BASE_URL !== "") {
        providers.push({ label: `Ollama (${OLLAMA_MODEL})`, run: reviewWithOllama });
    }

    return providers;
}

/**
 * Try each configured provider in order, retrying transient failures.
 *
 * @param {string} reviewPrompt Shared reviewer prompt.
 * @returns {Promise<{verdict: string, review: string}>} The first successful review.
 */
async function getReviewFromProviders(reviewPrompt) {
    const providers = buildProviderChain();

    // Guard: at least one provider must be configured to review anything.
    if (providers.length === EMPTY_LENGTH) {
        throw new Error("No review provider configured (set GEMINI_API_KEY, GROQ_API_KEY, or OLLAMA_BASE_URL).");
    }

    let lastError;

    for (const provider of providers) {
        try {
            console.log(`Requesting review from provider: ${provider.label}.`);

            return await withRetries(provider.label, () => provider.run(reviewPrompt));
        } catch (providerError) {
            lastError = providerError;

            console.warn(`Provider ${provider.label} failed: ${providerError.message}; falling through to the next provider.`);
        }
    }

    throw new Error(`All review providers failed. Last error: ${lastError.message}`);
}

/**
 * Validate a structured review payload.
 *
 * @param {unknown} reviewPayload Parsed Gemini JSON.
 * @returns {{verdict: string, review: string}} Validated review payload.
 */
export function validateReviewPayload(reviewPayload) {
    // Guard: reject malformed model output before submitting anything to Gitea.
    if (typeof reviewPayload !== "object" || reviewPayload === null) {
        throw new Error("Gemini review payload is not an object.");
    }

    const candidateReview = reviewPayload;

    // Guard: verdict must be one of the Gitea review events we support.
    if (!VALID_VERDICTS.includes(candidateReview.verdict)) {
        throw new Error(`Gemini review verdict is invalid: ${String(candidateReview.verdict)}`);
    }

    // Guard: review body must be markdown text for human readers.
    if (typeof candidateReview.review !== "string" || candidateReview.review.trim() === "") {
        throw new Error("Gemini review body is empty or invalid.");
    }

    return {
        verdict: candidateReview.verdict,
        review: candidateReview.review,
    };
}

/**
 * Build the hidden Night Shift review marker.
 *
 * @param {number} prNumber Gitea PR number.
 * @param {string} verdict Review verdict.
 * @param {Array<{pattern: string, line: string}>} secretFindings Secret findings.
 * @returns {string} HTML comment marker.
 */
function buildReviewMarker(prNumber, verdict, secretFindings) {
    const markerPayload = {
        pr_number: prNumber,
        verdict,
        base_branch: BASE_BRANCH,
        head_branch: HEAD_BRANCH,
        validation_profile: VALIDATION_PROFILE,
        max_attempts: PR_REVIEW_LOOP_MAX_ATTEMPTS,
        secret_findings_count: secretFindings.length,
    };

    return `${REVIEW_MARKER_PREFIX}${JSON.stringify(markerPayload)}${REVIEW_MARKER_SUFFIX}`;
}

/**
 * Format the final review body sent to Gitea.
 *
 * @param {number} prNumber Gitea PR number.
 * @param {{verdict: string, review: string}} reviewPayload Validated review payload.
 * @param {Array<{pattern: string, line: string}>} secretFindings Secret findings.
 * @returns {string} Markdown review body.
 */
function formatReviewBody(prNumber, reviewPayload, secretFindings) {
    const marker = buildReviewMarker(prNumber, reviewPayload.verdict, secretFindings);

    return [
        "### Automated Style Guide Review",
        "",
        `Verdict: ${reviewPayload.verdict}`,
        "",
        reviewPayload.review,
        "",
        marker,
        "",
        "Review generated by self-hosted PR reviewer.",
    ].join("\n");
}

/**
 * Build a blocking review when a diff appears to contain secrets.
 *
 * @param {Array<{pattern: string, line: string}>} secretFindings Secret findings.
 * @returns {{verdict: string, review: string}} Blocking review payload.
 */
function buildSecretBlockingReview(secretFindings) {
    const findingLines = secretFindings.map((finding) => {
        return `- ${finding.pattern}: \`${finding.line}\``;
    });

    return {
        verdict: "REQUEST_CHANGES",
        review: [
            "Secret-like content was detected in the added diff before Gemini review.",
            "The diff was not sent to Gemini. Remove or rotate the suspected secret, then push again.",
            "",
            ...findingLines,
        ].join("\n"),
    };
}

/**
 * Map an LLM verdict to a valid Gitea review event.
 *
 * @param {string} verdict One of the VALID_VERDICTS produced by the model.
 * @returns {string} A Gitea review event; unknown verdicts fall back to COMMENT.
 */
export function toGiteaReviewEvent(verdict) {
    // Guard: an unmapped verdict must NOT pass through unchanged, or Gitea would
    // drop it and leave an invisible PENDING draft. COMMENT keeps it visible.
    if (verdict in GITEA_REVIEW_EVENT_BY_VERDICT) {
        return GITEA_REVIEW_EVENT_BY_VERDICT[verdict];
    }

    return "COMMENT";
}

/**
 * Submit a PR review to Gitea.
 *
 * @param {number} prNumber Gitea PR number.
 * @param {string} verdict LLM verdict (mapped to a Gitea review event).
 * @param {string} reviewBody Markdown review body.
 * @returns {Promise<void>} Resolves after Gitea accepts the review.
 */
async function submitGiteaReview(prNumber, verdict, reviewBody) {
    const cleanApiUrl = GITEA_API_URL.replace(/\/$/, "");
    const reviewUrl = `${cleanApiUrl}/repos/${GITEA_REPOSITORY}/pulls/${prNumber}/reviews`;

    const response = await fetch(reviewUrl, {
        method: "POST",
        headers: {
            Authorization: `token ${GITEA_TOKEN}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            body: reviewBody,
            event: toGiteaReviewEvent(verdict),
        }),
    });

    const responseText = await response.text();

    // Guard: failed review posts must fail the workflow loudly.
    if (!isSuccessfulStatus(response.status)) {
        throw new Error(`Gitea review submit returned HTTP ${response.status}: ${responseText}`);
    }

    console.log(`Submitted ${verdict} review to PR #${prNumber}.`);
}

/**
 * Orchestrate the PR review.
 *
 * @returns {Promise<void>} Resolves when review completes.
 */
async function main() {
    console.log("Starting Gitea PR AI Reviewer.");

    // Guard: Gitea token is required because the workflow must write a review.
    if (GITEA_TOKEN === "") {
        throw new Error("GITEA_TOKEN is not defined.");
    }

    if (!GITEA_API_URL || !GITEA_REPOSITORY) throw new Error("Set GITEA_API_URL and GITEA_REPOSITORY explicitly.");
    const prNumber = Number.parseInt(PR_NUMBER_RAW, RADIX_DECIMAL);

    // Guard: PR number anchors the diff fetch and review endpoint.
    if (Number.isNaN(prNumber) || prNumber <= EMPTY_LENGTH) {
        throw new Error("PR_NUMBER is missing or invalid.");
    }

    const pullRequestDiff = await fetchPullRequestDiff(prNumber);

    // Guard: empty diffs do not need Gemini and should not produce noisy reviews.
    if (pullRequestDiff.trim().length === EMPTY_LENGTH) {
        console.log("PR diff is empty; skipping review.");

        return;
    }

    const secretFindings = findSecretLikeContent(pullRequestDiff);
    let reviewPayload;

    if (secretFindings.length > EMPTY_LENGTH) {
        reviewPayload = buildSecretBlockingReview(secretFindings);
    } else {
        // A configured provider is only needed after secret scanning clears the diff.
        const reviewPrompt = buildReviewPrompt(
            pullRequestDiff,
            readStyleGuide(JS_STYLE_PATH),
            readStyleGuide(TS_STYLE_PATH),
        );

        reviewPayload = await getReviewFromProviders(reviewPrompt);
    }

    const reviewBody = formatReviewBody(prNumber, reviewPayload, secretFindings);

    await submitGiteaReview(prNumber, reviewPayload.verdict, reviewBody);
}

/**
 * Return whether this module was run directly (vs imported by a test).
 *
 * @returns {boolean} True when node executed this file as the entry script.
 */
function isInvokedAsScript() {
    const scriptPath = process.argv[SECOND_ARRAY_INDEX];

    // Guard: when imported (e.g. by vitest) there is no matching entry script.
    if (!scriptPath) {
        return false;
    }

    return import.meta.url === pathToFileURL(scriptPath).href;
}

// Only run the workflow when executed as a script; tests import the helpers.
if (isInvokedAsScript()) {
    main()
        .then(() => {
            process.exit(EXIT_CODE_SUCCESS);
        })
        .catch((mainError) => {
            console.error(mainError.message);
            process.exit(EXIT_CODE_ERROR);
        });
}
