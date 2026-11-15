/**
 * Attaching stored media to a post.
 *
 * Alt text is required rather than optional. An attachment nobody can describe
 * is not a message, and requiring a description keeps the board's stated purpose
 * intact once binary files are allowed: a reader who cannot decode the file
 * still learns what the author says it is, and a reader who can decode it can
 * compare the two.
 *
 * Alt text is also part of what the author signs, because it travels in the
 * post's JSON body and the content hash covers it. Nobody can relabel someone
 * else's picture after the fact.
 */

import { MAX_ALT_LENGTH, type Env } from "../config.ts";
import { getMedia } from "../db.ts";
import { BoardError } from "../errors.ts";
import { stripInvisible } from "../validate.ts";

export interface Attachment {
    mediaId: string;
    alt: string;
    mediaType: string;
    kind: string;
    bytes: number;
    width: number | null;
    height: number | null;
}

const MEDIA_ID = /^[0-9A-Za-z_-]{43}$/;

/**
 * Reads the `attachments` field of a post payload and returns what the post may
 * link. Every id must already exist: upload first, then post, so a post is never
 * written referring to bytes the board does not hold.
 */
export async function resolveAttachments(
    env: Env,
    raw: unknown,
    maxAttachments: number,
): Promise<Attachment[]> {
    if (raw === undefined || raw === null) {
        return [];
    }
    if (!Array.isArray(raw)) {
        throw new BoardError(
            400,
            "bad_request",
            "attachments must be an array",
            "send attachments: [{ media_id, alt }]",
        );
    }
    if (raw.length > maxAttachments) {
        throw new BoardError(
            400,
            "bad_request",
            "too many attachments on one post",
            `at most ${maxAttachments} on this tier`,
            { limit: maxAttachments },
        );
    }
    const resolved: Attachment[] = [];
    const seen = new Set<string>();
    for (const entry of raw) {
        const attachment = await resolveOne(env, entry);
        // The same bytes twice in one post is a mistake worth naming: they carry
        // one id, so the second would collide on nothing and render twice.
        if (seen.has(attachment.mediaId)) {
            throw new BoardError(
                400,
                "bad_request",
                "the same media is attached twice",
                "attach each id once",
            );
        }
        seen.add(attachment.mediaId);
        resolved.push(attachment);
    }
    return resolved;
}

async function resolveOne(env: Env, entry: unknown): Promise<Attachment> {
    if (typeof entry !== "object" || entry === null) {
        throw new BoardError(400, "bad_request", "each attachment must be an object", "send { media_id, alt }");
    }
    const record = entry as Record<string, unknown>;
    const mediaId = typeof record.media_id === "string" ? record.media_id : "";
    if (!MEDIA_ID.test(mediaId)) {
        throw new BoardError(
            400,
            "bad_request",
            "media_id is not a media id",
            "POST /v1/media first and use the id it answers with",
        );
    }
    const row = await getMedia(env.DB, mediaId);
    if (row === null) {
        throw new BoardError(404, "media_not_found", "no such media", "upload the file before attaching it");
    }
    if (row.withheld === 1) {
        throw new BoardError(
            403,
            "media_not_found",
            "that attachment is withheld",
            "see /v1/moderation for the record",
        );
    }
    return {
        mediaId,
        alt: normalizeAlt(record.alt),
        mediaType: row.media_type,
        kind: row.kind,
        bytes: row.bytes,
        width: row.width,
        height: row.height,
    };
}

function normalizeAlt(value: unknown): string {
    if (typeof value !== "string") {
        throw new BoardError(
            400,
            "bad_request",
            "every attachment needs alt text",
            "say what the file is, in a sentence a reader who cannot open it can use",
        );
    }
    const cleaned = stripInvisible(value).trim();
    if (cleaned.length === 0) {
        throw new BoardError(
            400,
            "bad_request",
            "alt text is empty",
            "say what the file is, in a sentence a reader who cannot open it can use",
        );
    }
    if (cleaned.length > MAX_ALT_LENGTH) {
        throw new BoardError(400, "bad_request", "alt text is too long", `at most ${MAX_ALT_LENGTH} characters`);
    }
    return cleaned;
}

/**
 * What the post's content hash covers.
 *
 * A post with no attachments hashes exactly as it did before this feature
 * existed, so every hash already published stays correct. A post with
 * attachments adds one canonical line per attachment, which binds the id and the
 * alt text to the body: relabelling either changes the hash the author signed.
 */
export function hashInput(body: string, attachments: readonly Attachment[]): string {
    if (attachments.length === 0) {
        return body;
    }
    const lines = attachments.map((item) => `bulletin-media:v1:${item.mediaId}:${item.alt}`);
    return `${body}\n${lines.join("\n")}`;
}

/** The shape a reader sees, in the feed and in the live stream alike. */
export function publicAttachment(item: Attachment): Record<string, unknown> {
    return {
        media_id: item.mediaId,
        alt: item.alt,
        media_type: item.mediaType,
        kind: item.kind,
        bytes: item.bytes,
        width: item.width,
        height: item.height,
        url: `/v1/media/${item.mediaId}`,
    };
}
