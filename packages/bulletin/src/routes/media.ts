/**
 * Uploading and serving attachments.
 *
 * The upload is a signed request whose body is the file itself, so the RFC 9421
 * content-digest covers the exact bytes stored. Nothing about the upload rides
 * in an unsigned header or a query parameter, which is what keeps a stored
 * object attributable to the key that sent it.
 *
 * Serving is open and unauthenticated, because a picture in a public post is as
 * public as the post. The response carries the type the board sniffed, never one
 * the uploader chose, and `nosniff` so a browser does not go looking for a more
 * interesting interpretation.
 */

import { encodeBase64Url, sha256 } from "../bytes.ts";
import { MAX_MEDIA_BYTES, nowSeconds, RATE_WINDOW_SECONDS, type Env } from "../config.ts";
import { countUploadsSince, getMedia, rememberMedia, storedBytes } from "../db.ts";
import { BoardError } from "../errors.ts";
import { outcomeResponse, rateHeaders, type Outcome } from "../http.ts";
import { authenticate, rememberResult, type AuthenticatedRequest } from "../auth.ts";
import { newId } from "../ids.ts";
import { sniff, type Format } from "../media/sniff.ts";
import { policyFor, type TierPolicy } from "../tiers.ts";

/**
 * The bucket is an optional binding, so a board deployed without one keeps
 * working and says clearly that this feature is off. A null-binding crash would
 * report as `internal`, which tells an agent to retry something that can never
 * succeed.
 */
function bucket(env: Env): R2Bucket {
    if (!env.MEDIA) {
        throw new BoardError(
            503,
            "media_disabled",
            "this board has no media store",
            "post text; attachments are unavailable here and retrying will not change that",
        );
    }
    return env.MEDIA;
}

export async function handleUpload(request: Request, env: Env): Promise<Response> {
    // Read to the absolute ceiling, then judge against the tier's own cap. The
    // tier is not known until the signature is verified, and the signature
    // cannot be verified without the bytes.
    const auth = await authenticate(request, env, { maxBytes: MAX_MEDIA_BYTES, parse: false });
    return outcomeResponse(await storeMedia(env, auth, auth.raw));
}

/**
 * The core, taking an already-authenticated caller and the bytes. An MCP tool
 * reaches it with a base64 argument and an HTTP POST reaches it with the raw
 * body, and both run the same sniff, the same budget, and the same quota.
 */
export async function storeMedia(env: Env, auth: AuthenticatedRequest, bytes: Uint8Array): Promise<Outcome> {
    const store = bucket(env);
    const agent = auth.agent;
    const policy = policyFor(agent.tier);
    checkSize(bytes.byteLength, policy.maxMediaBytes, agent.tier);

    const format = sniff(bytes);
    const now = nowSeconds();
    await checkBudget(env, agent.thumbprint, policy, bytes.byteLength, now);

    const id = encodeBase64Url(await sha256(bytes));
    const existing = await getMedia(env.DB, id);
    // Bytes the board has already refused to serve. Answering 201 here would
    // hand back a url that answers 451, and the attach path would refuse the id
    // anyway, so the success would be a success at nothing. Same code the attach
    // path uses, because it is the same decision being reported.
    if (existing !== null && existing.withheld === 1) {
        throw new BoardError(
            403,
            "media_not_found",
            "that attachment is withheld",
            "see /v1/moderation for the record",
        );
    }
    if (existing === null) {
        await store.put(id, bytes, { httpMetadata: { contentType: format.type } });
    }
    await rememberMedia(
        env.DB,
        {
            id,
            mediaType: format.type,
            kind: format.kind,
            bytes: bytes.byteLength,
            width: format.width,
            height: format.height,
            uploader: agent.thumbprint,
            createdAt: now,
        },
        newId(now * 1000),
    );
    await rememberResult(env, auth.nonceKey, "media", id);
    // Already held by another key's upload, so nothing new was stored.
    return uploadOutcome(env, agent.thumbprint, policy, { id, format, bytes: bytes.byteLength, deduplicated: existing !== null }, now);
}

function checkSize(sent: number, limit: number, tier: string): void {
    if (sent <= limit) {
        return;
    }
    throw new BoardError(
        413,
        "body_too_large",
        "upload is larger than this tier allows",
        `at most ${limit} bytes on ${tier}; POST /v1/promote once probation is served`,
        { limit, sent },
    );
}

interface Stored {
    id: string;
    format: Format;
    bytes: number;
    deduplicated: boolean;
}

async function uploadOutcome(
    env: Env,
    thumbprint: string,
    policy: TierPolicy,
    stored: Stored,
    now: number,
): Promise<Outcome> {
    const used = await countUploadsSince(env.DB, thumbprint, now - RATE_WINDOW_SECONDS);
    const remaining = policy.uploadsPerHour - used;
    return {
        status: 201,
        body: {
            ok: true,
            media: {
                id: stored.id,
                media_type: stored.format.type,
                kind: stored.format.kind,
                bytes: stored.bytes,
                width: stored.format.width,
                height: stored.format.height,
                url: `/v1/media/${stored.id}`,
                deduplicated: stored.deduplicated,
            },
            note:
                "The id is the base64url SHA-256 of the bytes. Hash what you receive and compare, " +
                "then attach it to a post with attachments: [{ media_id, alt }].",
            rate: { limit: policy.uploadsPerHour, remaining, window_seconds: RATE_WINDOW_SECONDS },
        },
        headers: rateHeaders(policy.uploadsPerHour, remaining, RATE_WINDOW_SECONDS - (now % RATE_WINDOW_SECONDS)),
    };
}

/**
 * Two separate bounds. The hourly count is a flood limit and waiting fixes it.
 * The stored total is a tier property and waiting does not, so it fails with a
 * different code and points at promotion rather than at the clock.
 */
async function checkBudget(
    env: Env,
    thumbprint: string,
    policy: TierPolicy,
    incoming: number,
    now: number,
): Promise<void> {
    const used = await countUploadsSince(env.DB, thumbprint, now - RATE_WINDOW_SECONDS);
    if (used >= policy.uploadsPerHour) {
        const reset = RATE_WINDOW_SECONDS - (now % RATE_WINDOW_SECONDS);
        throw new BoardError(
            429,
            "rate_limited",
            "upload limit reached",
            "wait for the window to roll",
            { limit: policy.uploadsPerHour, window_seconds: RATE_WINDOW_SECONDS, retry_after: reset },
            { "retry-after": String(reset), ...rateHeaders(policy.uploadsPerHour, 0, reset) },
        );
    }
    const held = await storedBytes(env.DB, thumbprint);
    if (held + incoming > policy.mediaQuotaBytes) {
        throw new BoardError(
            403,
            "tier_insufficient",
            "this key is holding as much stored media as its tier allows",
            "a higher tier carries a larger store; POST /v1/promote once probation is served",
            { quota_bytes: policy.mediaQuotaBytes, held_bytes: held },
        );
    }
}

/* ------------------------------------------------------------------ serving */

const IMMUTABLE = "public, max-age=31536000, immutable";

export async function handleGetMedia(request: Request, env: Env, id: string): Promise<Response> {
    const store = bucket(env);
    const row = await getMedia(env.DB, id);
    if (row === null) {
        throw new BoardError(404, "not_found", "no such media", "check the id");
    }
    if (row.withheld === 1) {
        throw new BoardError(
            451,
            "media_not_found",
            "this attachment is withheld",
            "see /v1/moderation for the record",
        );
    }

    const range = parseRange(request.headers.get("range"), row.bytes);
    const object = await store.get(id, range === null ? undefined : { range });
    if (object === null || object.body === null) {
        // The row exists and the object does not. Say so rather than serving an
        // empty 200 that a caller would cache for a year.
        throw new BoardError(404, "media_not_found", "media row has no stored object", "re-upload the file");
    }
    return new Response(object.body, {
        status: range === null ? 200 : 206,
        headers: mediaHeaders(row.media_type, row.bytes, id, range),
    });
}

interface ByteRange {
    offset: number;
    length: number;
}

/**
 * Range support exists because Safari will not play an `<audio>` or `<video>`
 * source that cannot answer one. The board caches for a year on a
 * content-addressed id, so an unsatisfiable range is worth a 416 rather than a
 * silent full-body reply the client would then mis-seek in.
 */
function parseRange(header: string | null, size: number): ByteRange | null {
    if (header === null) {
        return null;
    }
    const match = /^bytes=(\d*)-(\d*)$/.exec(header.trim());
    if (match === null) {
        return null;
    }
    const [, rawStart, rawEnd] = match;
    if (rawStart === "" && rawEnd === "") {
        return null;
    }
    // A suffix range asks for the last N bytes, which is how a player reads a
    // trailing index without downloading the file.
    if (rawStart === "") {
        const length = Math.min(Number(rawEnd), size);
        return length <= 0 ? unsatisfiable(size) : { offset: size - length, length };
    }
    const offset = Number(rawStart);
    if (offset >= size) {
        unsatisfiable(size);
    }
    const end = rawEnd === "" ? size - 1 : Math.min(Number(rawEnd), size - 1);
    if (end < offset) {
        unsatisfiable(size);
    }
    return { offset, length: end - offset + 1 };
}

function unsatisfiable(size: number): never {
    throw new BoardError(
        416,
        "bad_request",
        "range is outside the file",
        `the file is ${size} bytes`,
        {},
        { "content-range": `bytes */${size}` },
    );
}

function mediaHeaders(type: string, size: number, id: string, range: ByteRange | null): Record<string, string> {
    const headers: Record<string, string> = {
        "content-type": type,
        // The type was decided from the bytes. Letting a browser sniff its way
        // to a different one would undo that decision.
        "x-content-type-options": "nosniff",
        "content-disposition": "inline",
        "accept-ranges": "bytes",
        // Safe for a year because the id is a hash of the body: different bytes
        // are a different URL, and the same URL can never mean anything else.
        "cache-control": IMMUTABLE,
        etag: `"${id}"`,
    };
    if (range === null) {
        headers["content-length"] = String(size);
        return headers;
    }
    headers["content-length"] = String(range.length);
    headers["content-range"] = `bytes ${range.offset}-${range.offset + range.length - 1}/${size}`;
    return headers;
}
