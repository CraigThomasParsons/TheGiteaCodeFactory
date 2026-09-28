/**
 * Unit tests for the Autonomous PR Reviewer's provider-chain helpers.
 *
 * What: covers retry classification, fence-tolerant JSON parsing, review
 *       payload validation, prompt assembly, and the backoff retry loop.
 * Why: the reviewer fans out across Gemini -> Groq -> local Ollama with retry,
 *      and these pure helpers decide whether a failure is retried, fallen
 *      through, or trusted — so they must be locked down without network calls.
 * How: `node --test scripts/tools/tests/ai_pr_reviewer.test.js` (no extra deps;
 *      the project's vitest suite is scoped to the game engine, not tools).
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
    buildReviewPrompt,
    findSecretLikeContent,
    isRetryableStatus,
    looksLikeHighEntropySecret,
    parseJsonObject,
    shannonEntropyBitsPerChar,
    toGiteaReviewEvent,
    validateReviewPayload,
    withRetries,
} from "../ai_pr_reviewer.js";

const HTTP_OK = 200;
const HTTP_BAD_REQUEST = 400;
const HTTP_UNAUTHORIZED = 401;
const HTTP_NOT_FOUND = 404;
const HTTP_TOO_MANY_REQUESTS = 429;
const HTTP_INTERNAL_SERVER_ERROR = 500;
const HTTP_SERVICE_UNAVAILABLE = 503;

describe("isRetryableStatus", () => {
    it("treats 429 and 5xx as retryable transient failures", () => {
        assert.equal(isRetryableStatus(HTTP_TOO_MANY_REQUESTS), true);
        assert.equal(isRetryableStatus(HTTP_INTERNAL_SERVER_ERROR), true);
        assert.equal(isRetryableStatus(HTTP_SERVICE_UNAVAILABLE), true);
    });

    it("treats 2xx and other 4xx as non-retryable caller errors", () => {
        assert.equal(isRetryableStatus(HTTP_OK), false);
        assert.equal(isRetryableStatus(HTTP_BAD_REQUEST), false);
        assert.equal(isRetryableStatus(HTTP_UNAUTHORIZED), false);
        assert.equal(isRetryableStatus(HTTP_NOT_FOUND), false);
    });
});

describe("parseJsonObject", () => {
    it("parses a bare JSON object", () => {
        const parsed = parseJsonObject('{"verdict":"APPROVE","review":"ok"}');
        assert.equal(parsed.verdict, "APPROVE");
    });

    it("strips ```json code fences before parsing", () => {
        const fenced = '```json\n{"verdict":"COMMENT","review":"note"}\n```';
        const parsed = parseJsonObject(fenced);
        assert.equal(parsed.verdict, "COMMENT");
        assert.equal(parsed.review, "note");
    });

    it("strips bare ``` fences and surrounding whitespace", () => {
        const fenced = '\n```\n{"verdict":"REQUEST_CHANGES","review":"fix"}\n```\n';
        const parsed = parseJsonObject(fenced);
        assert.equal(parsed.verdict, "REQUEST_CHANGES");
    });

    it("extracts the object when a model wraps it in prose (mammouth case)", () => {
        const prose = 'Here is the review you asked for:\n{"verdict":"APPROVE","review":"ok"}\nLet me know if you need more.';
        const parsed = parseJsonObject(prose);
        assert.equal(parsed.verdict, "APPROVE");
        assert.equal(parsed.review, "ok");
    });
});

describe("validateReviewPayload", () => {
    it("returns the normalized payload for valid input", () => {
        const result = validateReviewPayload({ verdict: "APPROVE", review: "looks good" });
        assert.deepEqual(result, { verdict: "APPROVE", review: "looks good" });
    });

    it("rejects an unknown verdict", () => {
        assert.throws(() => validateReviewPayload({ verdict: "MAYBE", review: "x" }));
    });

    it("rejects an empty review body", () => {
        assert.throws(() => validateReviewPayload({ verdict: "APPROVE", review: "   " }));
    });

    it("rejects a non-object payload", () => {
        assert.throws(() => validateReviewPayload(null));
    });
});

describe("shannonEntropyBitsPerChar", () => {
    it("scores readable identifiers below the secret threshold", () => {
        assert.ok(shannonEntropyBitsPerChar("REVIEW_EVENT_BY_VERDICT") < 3.5);
    });

    it("scores random tokens above the secret threshold", () => {
        assert.ok(shannonEntropyBitsPerChar("aB3xK9pLmN2qR7sT4vW8") >= 3.5);
    });

    it("returns 0 for empty input", () => {
        assert.equal(shannonEntropyBitsPerChar(""), 0);
    });
});

describe("looksLikeHighEntropySecret", () => {
    it("rejects a SCREAMING_SNAKE_CASE identifier, accepts a random token", () => {
        assert.equal(looksLikeHighEntropySecret("REVIEW_EVENT_BY_VERDICT"), false);
        assert.equal(looksLikeHighEntropySecret("aB3xK9pLmN2qR7sT4vW8"), true);
    });
});

describe("findSecretLikeContent", () => {
    it("does NOT flag a SCREAMING_SNAKE_CASE constant name (the reported false positive)", () => {
        assert.equal(findSecretLikeContent("+const GITEA_REVIEW_EVENT_BY_VERDICT = {").length, 0);
    });

    it("flags a real high-entropy gitea/github token", () => {
        const findings = findSecretLikeContent("+const leaked = gho_16C7e42F292c6912E7710c8aB3xK9pL;");
        assert.ok(findings.some((finding) => finding.pattern === "github-or-gitea-token"));
    });

    it("does NOT flag a low-entropy string that only matches structurally (entropy gate)", () => {
        assert.equal(findSecretLikeContent("+const value = gitea_aaaaaaaaaaaaaaaaaaaa;").length, 0);
    });

    it("always flags a private key block (no entropy gate)", () => {
        const findings = findSecretLikeContent("+-----BEGIN RSA PRIVATE KEY-----");
        assert.ok(findings.some((finding) => finding.pattern === "private-key"));
    });
});

describe("toGiteaReviewEvent", () => {
    it("maps APPROVE to Gitea's APPROVED (the bug that left reviews PENDING)", () => {
        assert.equal(toGiteaReviewEvent("APPROVE"), "APPROVED");
    });

    it("passes through verdicts that are already valid Gitea events", () => {
        assert.equal(toGiteaReviewEvent("REQUEST_CHANGES"), "REQUEST_CHANGES");
        assert.equal(toGiteaReviewEvent("COMMENT"), "COMMENT");
    });

    it("falls back to COMMENT for an unknown verdict (never a PENDING draft)", () => {
        assert.equal(toGiteaReviewEvent("SOMETHING_ELSE"), "COMMENT");
    });
});

describe("buildReviewPrompt", () => {
    it("embeds the diff and both style guides", () => {
        const prompt = buildReviewPrompt("+const value = 1;", "JS-STYLE-MARKER", "TS-STYLE-MARKER");
        assert.ok(prompt.includes("+const value = 1;"));
        assert.ok(prompt.includes("JS-STYLE-MARKER"));
        assert.ok(prompt.includes("TS-STYLE-MARKER"));
        assert.ok(prompt.includes('"verdict"'));
    });
});

describe("withRetries", () => {
    it("returns the first successful result without retrying", async () => {
        let callCount = 0;
        const attempt = async () => {
            callCount += 1;

            return { verdict: "APPROVE", review: "ok" };
        };

        const result = await withRetries("Test", attempt);

        assert.equal(result.verdict, "APPROVE");
        assert.equal(callCount, 1);
    });

    it("does not retry a non-retryable error", async () => {
        let callCount = 0;
        const attempt = async () => {
            callCount += 1;

            throw new Error("bad request");
        };

        await assert.rejects(withRetries("Test", attempt), /bad request/);
        assert.equal(callCount, 1);
    });

    it("retries a retryable failure and then succeeds", async () => {
        let callCount = 0;
        const attempt = async () => {
            callCount += 1;

            // First attempt fails transiently; the backoff loop must retry it.
            if (callCount === 1) {
                const transientError = new Error("overloaded");
                transientError.retryable = true;

                throw transientError;
            }

            return { verdict: "COMMENT", review: "second try" };
        };

        const result = await withRetries("Test", attempt);

        assert.equal(result.review, "second try");
        assert.equal(callCount, 2);
    });
});

