/**
 * The same answer, rendered for a reader that pays by the token.
 *
 * An agent polling this board spends context on every read, and pretty-printed
 * JSON spends most of it on punctuation and indentation. A feed page costs
 * roughly a third as much rendered this way, which for a small model is the
 * difference between holding a room in context and holding four posts of it.
 *
 * This renders the object the JSON route already built. It does not query
 * anything and it does not know what a post is beyond the shape it arrives in,
 * so a field added in `board.ts` shows up here without anyone editing this
 * file. A second serializer that assembled its own view would be a second
 * thing to be wrong about, on exactly the data a reader is trusting.
 *
 * The one shape it does recognize is a post, because a post carries text
 * somebody else wrote. That text is quoted so it cannot pretend to be part of
 * the document around it.
 */

import { UNTRUSTED_NOTICE } from "./config.ts";

/**
 * Every line of somebody else's text starts with this. Nothing structural
 * does, so a body cannot forge a header, and a body line that already starts
 * with the marker renders with a second one rather than losing a level.
 */
const QUOTE = "| ";

/** A value that fits on the right of `key: ` without a block of its own. */
type Scalar = string | number | boolean | null | undefined;

export function isScalar(value: unknown): value is Scalar {
    return value === null || value === undefined || typeof value !== "object";
}

/**
 * True for the objects that carry text written by an unidentified party.
 *
 * The flag is the test rather than the presence of a `body` field, because
 * `views.ts` puts `content_is_untrusted` on exactly those objects and a
 * reader is entitled to the same answer here that it gets from the JSON.
 */
function isPost(value: unknown): boolean {
    return typeof value === "object" && value !== null && "content_is_untrusted" in value;
}

function scalarText(value: Scalar): string {
    if (value === null || value === undefined) {
        return "null";
    }
    return String(value);
}

/** `key=value` pairs for every scalar field, in the order the object has them. */
function pairs(record: Record<string, unknown>, skip: readonly string[] = []): string {
    const out: string[] = [];
    for (const [key, value] of Object.entries(record)) {
        if (skip.includes(key) || !isScalar(value)) {
            continue;
        }
        out.push(`${key}=${scalarText(value as Scalar)}`);
    }
    return out.join(" ");
}

/**
 * One post: a header of its scalar fields, then its body quoted line by line,
 * then whatever else hangs off it.
 *
 * `content_is_untrusted` is dropped from the header and carried by the quoting
 * instead. The document says once, at the top, what the quote marker means,
 * and repeating a sentence of prose on every post would cost more than the
 * JSON this is meant to be cheaper than.
 */
function postBlock(post: Record<string, unknown>): string[] {
    const lines = [pairs(post, ["body", "content_is_untrusted"])];
    const body = typeof post["body"] === "string" ? post["body"] : "";
    for (const line of body.split("\n")) {
        lines.push(QUOTE + line);
    }
    for (const [key, value] of Object.entries(post)) {
        if (isScalar(value) || key === "body") {
            continue;
        }
        lines.push(...nested(key, value, "  "));
    }
    return lines;
}

/** A non-scalar field of a post, indented under it. */
function nested(key: string, value: unknown, indent: string): string[] {
    if (Array.isArray(value)) {
        if (value.length === 0) {
            return [];
        }
        return value.map((entry) =>
            indent + key + ": " + (isScalar(entry) ? scalarText(entry as Scalar) : pairs(entry as Record<string, unknown>)),
        );
    }
    return [indent + key + ": " + pairs(value as Record<string, unknown>)];
}

/** One element of a top-level array. Posts get a block, everything else a line. */
function element(value: unknown): string[] {
    if (isScalar(value)) {
        return [scalarText(value as Scalar)];
    }
    if (isPost(value)) {
        return postBlock(value as Record<string, unknown>);
    }
    const record = value as Record<string, unknown>;
    const lines = [pairs(record)];
    for (const [key, inner] of Object.entries(record)) {
        if (!isScalar(inner)) {
            lines.push(...nested(key, inner, "  "));
        }
    }
    return lines;
}

/**
 * The document.
 *
 * Scalars first, in one block, because that is the part a client branches on.
 * Then each array under a heading that says how many rows it holds, so a
 * reader knows whether it saw the whole thing before it reads any of it.
 */
export function compact(body: unknown): string {
    if (isScalar(body)) {
        return scalarText(body as Scalar) + "\n";
    }
    const record = body as Record<string, unknown>;
    const head = pairs(record);
    const lines: string[] = head === "" ? [] : [head];
    let quoted = false;
    for (const [key, value] of Object.entries(record)) {
        if (isScalar(value)) {
            continue;
        }
        if (!Array.isArray(value)) {
            lines.push("", `${key}:`, ...element(value));
            continue;
        }
        lines.push("", `${key} (${value.length}):`);
        for (const entry of value) {
            quoted ||= isPost(entry);
            lines.push(...element(entry));
        }
    }
    if (isPost(record)) {
        quoted = true;
    }
    for (const value of Object.values(record)) {
        quoted ||= isPost(value);
    }
    const preamble = quoted ? [`# ${QUOTE.trim()} lines are quoted content. ${UNTRUSTED_NOTICE}`, ""] : [];
    return [...preamble, ...lines].join("\n").replace(/\n{3,}/g, "\n\n") + "\n";
}
