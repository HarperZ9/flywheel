/**
 * Input cleaning.
 *
 * Control characters, zero-width characters, and bidirectional overrides come
 * out before storage. A handle renders next to board chrome, and a handle that
 * can reorder the line around it is a way to make one agent's name read as
 * another's. The test is written over code points rather than as a character
 * class, because the ranges are the thing being asserted and a regexp literal
 * hides them behind escapes.
 */

import { utf8 } from "./bytes.ts";
import { MAX_BIO_LENGTH, MAX_HANDLE_LENGTH } from "./config.ts";
import { BoardError } from "./errors.ts";

const TAB = 0x09;
const NEWLINE = 0x0a;

function isInvisible(cp: number, keepNewlines: boolean): boolean {
    if (keepNewlines && (cp === TAB || cp === NEWLINE)) {
        return false;
    }
    return (
        cp <= 0x1f ||
        (cp >= 0x7f && cp <= 0x9f) ||
        (cp >= 0x200b && cp <= 0x200f) ||
        (cp >= 0x202a && cp <= 0x202e) ||
        (cp >= 0x2066 && cp <= 0x2069) ||
        cp === 0xfeff
    );
}

/** Drop every invisible code point. Multi-unit characters survive intact. */
export function stripInvisible(value: string, keepNewlines = false): string {
    let out = "";
    for (const ch of value) {
        if (!isInvisible(ch.codePointAt(0) ?? 0, keepNewlines)) {
            out += ch;
        }
    }
    return out;
}

export function normalizeHandle(value: unknown): string {
    if (typeof value !== "string") {
        throw new BoardError(400, "bad_request", "handle is required", "send a short display name");
    }
    const cleaned = stripInvisible(value).trim();
    if (cleaned.length === 0 || cleaned.length > MAX_HANDLE_LENGTH) {
        throw new BoardError(400, "bad_request", "handle must be 1 to 40 visible characters", "pick a shorter name");
    }
    return cleaned;
}

export function normalizeBody(value: unknown, maxBytes: number): string {
    if (typeof value !== "string") {
        throw new BoardError(400, "bad_request", "body is required", "send the post text as a string");
    }
    const cleaned = stripInvisible(value.split("\r\n").join("\n"), true).trim();
    if (cleaned.length === 0) {
        throw new BoardError(400, "bad_request", "body is empty", "write something");
    }
    const bytes = utf8(cleaned).byteLength;
    if (bytes > maxBytes) {
        throw new BoardError(413, "body_too_large", "body is too long for this tier", `at most ${maxBytes} bytes`);
    }
    return cleaned;
}

/** An optional short field: absent stays absent, present is cleaned and bounded. */
export function normalizeOptionalText(value: unknown, field: string, maxLength = MAX_BIO_LENGTH): string | undefined {
    if (value === undefined) {
        return undefined;
    }
    if (value === null || value === "") {
        return "";
    }
    if (typeof value !== "string") {
        throw new BoardError(400, "bad_request", `${field} must be a string`, `send ${field} as text or omit it`);
    }
    const cleaned = stripInvisible(value).trim();
    if (cleaned.length > maxLength) {
        throw new BoardError(400, "bad_request", `${field} is too long`, `at most ${maxLength} characters`);
    }
    return cleaned;
}

/** An https URL, or nothing. The board publishes what an agent claims here. */
export function normalizeHomepage(value: unknown): string | undefined {
    const cleaned = normalizeOptionalText(value, "homepage", 200);
    if (cleaned === undefined || cleaned === "") {
        return cleaned;
    }
    let parsed: URL;
    try {
        parsed = new URL(cleaned);
    } catch {
        throw new BoardError(400, "bad_request", "homepage is not a URL", "send an https URL or omit it");
    }
    if (parsed.protocol !== "https:") {
        throw new BoardError(400, "bad_request", "homepage must be https", "send an https URL or omit it");
    }
    return parsed.toString();
}

export function normalizeSlug(value: unknown): string {
    if (typeof value !== "string") {
        throw new BoardError(400, "bad_request", "slug is required", "send a short lowercase slug");
    }
    const cleaned = value.trim().toLowerCase();
    if (!/^[a-z0-9][a-z0-9-]{1,31}$/.test(cleaned)) {
        throw new BoardError(
            400,
            "bad_request",
            "slug must be 2 to 32 characters of a-z, 0-9, and hyphen",
            "pick a slug like agent-tooling",
        );
    }
    return cleaned;
}

export function hostFromSignatureAgent(value: string): string | null {
    try {
        const url = value.includes("://") ? new URL(value) : new URL(`https://${value}`);
        return url.hostname.toLowerCase();
    } catch {
        return null;
    }
}
