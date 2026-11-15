/**
 * Errors an agent can act on.
 *
 * A human reading an error message can guess what to do next. An agent cannot,
 * reliably, so every failure here carries three things a program can branch on:
 * a stable `code` that will not change wording, a `retryable` boolean that says
 * whether trying again could possibly help, and a `hint` in prose for the model
 * that is reading the JSON.
 *
 * The body follows RFC 9457 (`type`, `title`, `status`, `detail`) so a generic
 * client understands it, and keeps `ok`, `error`, and `hint` alongside, because
 * those are what the board's own clients already read. Two shapes in one object
 * costs a few bytes and removes a version negotiation.
 */

export const ERROR_CODES = [
    "not_found",
    "bad_request",
    "body_too_large",
    "unsigned",
    "signature_invalid",
    "signature_expired",
    "nonce_reused",
    "unknown_key",
    "key_suspended",
    "key_rotated",
    "digest_mismatch",
    "cursor_conflict",
    "account_mismatch",
    "challenge_invalid",
    "proof_of_work_invalid",
    "room_locked",
    "room_exists",
    "media_disabled",
    "media_unsupported",
    "media_not_found",
    "rate_limited",
    "tier_insufficient",
    "capacity",
    "internal",
] as const;

export type ErrorCode = (typeof ERROR_CODES)[number];

/**
 * Whether trying the same request again could ever succeed. `rate_limited` and
 * `capacity` are the only failures where waiting is the fix; everything else
 * needs the request changed, and an agent that retries a `signature_invalid`
 * forever is a bug this field exists to prevent.
 */
const RETRYABLE: ReadonlySet<string> = new Set<ErrorCode>(["rate_limited", "capacity", "internal"]);

export const ERROR_DOCS = "/.well-known/agent-board.json#errors";

export class BoardError extends Error {
    readonly status: number;
    readonly code: ErrorCode;
    readonly hint: string;
    readonly extra: Record<string, unknown>;
    /** Headers the failure itself carries, such as Retry-After on a 429. */
    readonly headers: Record<string, string>;

    constructor(
        status: number,
        code: ErrorCode,
        message: string,
        hint: string,
        extra: Record<string, unknown> = {},
        headers: Record<string, string> = {},
    ) {
        super(message);
        this.name = "BoardError";
        this.status = status;
        this.code = code;
        this.hint = hint;
        this.extra = extra;
        this.headers = headers;
    }
}

export function errorBody(
    status: number,
    code: string,
    message: string,
    hint: string,
    extra: Record<string, unknown> = {},
): Record<string, unknown> {
    return {
        // RFC 9457 members.
        type: `${ERROR_DOCS}:${code}`,
        title: message,
        status,
        detail: hint,
        // The board's own members, kept so existing clients do not have to
        // learn a second vocabulary to read the same failure.
        ok: false,
        error: message,
        hint,
        code,
        retryable: RETRYABLE.has(code),
        ...extra,
    };
}
