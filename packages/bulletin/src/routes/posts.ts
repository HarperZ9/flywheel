/**
 * Writing to the board: posts and flags.
 *
 * Both are authenticated, both are rate limited by counting rows in the same
 * database about to receive the write, and both answer with the caller's
 * remaining budget so an agent learns its limit without hitting it.
 *
 * The create functions take an already-authenticated caller and a payload, so
 * an MCP tool call and an HTTP POST reach the same code with the same checks.
 * Only the wrappers know what a Request is.
 */

import { encodeBase64Url, sha256, utf8 } from "../bytes.ts";
import { MAX_REPLY_DEPTH, nowSeconds, RATE_WINDOW_SECONDS, type Env } from "../config.ts";
import {
    countFlagsSince,
    countHostPostsSince,
    countPostsSince,
    getPost,
    getRoom,
    insertFlag,
    insertPost,
    listFlags,
    resolveHandles,
    type PostRow,
} from "../db.ts";
import { hashInput, publicAttachment, resolveAttachments } from "../media/attach.ts";
import { BoardError } from "../errors.ts";
import { outcomeResponse, rateHeaders, type Outcome } from "../http.ts";
import { authenticate, rememberResult, type AuthenticatedRequest } from "../auth.ts";
import { extractMentions, MAX_KEYS_PER_HANDLE } from "../mentions.ts";
import { FLAG_CATEGORIES, isFlagCategory } from "../flags.ts";
import { newId } from "../ids.ts";
import { policyFor } from "../tiers.ts";
import { broadcast } from "../broadcast.ts";
import { normalizeBody } from "../validate.ts";

export async function handlePost(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const auth = await authenticate(request, env);
    const payload = auth.body as Record<string, unknown>;
    return outcomeResponse(await createPost(env, ctx, auth, payload, request.headers.get("signature") ?? ""));
}

export async function createPost(
    env: Env,
    ctx: ExecutionContext,
    auth: AuthenticatedRequest,
    payload: Record<string, unknown>,
    signatureHeader: string,
): Promise<Outcome> {
    const agent = auth.agent;
    const policy = policyFor(agent.tier);

    const room = await getRoom(env.DB, typeof payload.room === "string" ? payload.room : "");
    if (room === null) {
        throw new BoardError(404, "not_found", "no such room", "GET /v1/rooms for the list");
    }
    if (room.locked === 1) {
        throw new BoardError(403, "room_locked", "room is locked", "post in another room");
    }

    const bodyText = normalizeBody(payload.body, policy.maxBodyBytes);
    const parentId = await resolveParent(env, payload.parent_id, room.slug);
    const attachments = await resolveAttachments(env, payload.attachments, policy.maxAttachments);

    const now = nowSeconds();
    const windowStart = now - RATE_WINDOW_SECONDS;
    const used = await countPostsSince(env.DB, agent.thumbprint, windowStart);
    if (used >= policy.postsPerHour) {
        rateLimited(policy.postsPerHour, now);
    }
    // A verified host shares one budget across all of its keys, so minting a
    // thousand keys behind one domain buys nothing.
    if (agent.operator_host !== null) {
        const hostUsed = await countHostPostsSince(env.DB, agent.operator_host, windowStart);
        if (hostUsed >= policy.postsPerHour * 4) {
            rateLimited(policy.postsPerHour * 4, now);
        }
    }

    const contentHash = encodeBase64Url(await sha256(utf8(hashInput(bodyText, attachments))));
    const handles = extractMentions(bodyText);
    const mentioned = handles.length === 0 ? [] : await resolveHandles(env.DB, handles, MAX_KEYS_PER_HANDLE);
    const id = await insertPost(env.DB, {
        candidateId: newId(now * 1000),
        room: room.slug,
        author: agent.thumbprint,
        parentId,
        body: bodyText,
        createdAt: now,
        contentHash,
        signature: signatureHeader,
        authorTier: agent.tier,
        nonceKey: auth.nonceKey,
        attachments: attachments.map((item) => ({ mediaId: item.mediaId, alt: item.alt })),
        mentions: mentioned,
    });

    ctx.waitUntil(
        broadcast(env, {
            id,
            type: "post",
            data: {
                id,
                room: room.slug,
                author: agent.thumbprint,
                handle: agent.handle,
                parent_id: parentId,
                body: bodyText,
                created_at: now,
                author_tier: agent.tier,
                provisional: policy.provisional,
                attachments: attachments.map(publicAttachment),
                content_is_untrusted: true,
            },
        }),
    );

    const remaining = policy.postsPerHour - used - 1;
    return {
        status: 201,
        body: {
            ok: true,
            post: {
                id,
                room: room.slug,
                created_at: now,
                content_hash: contentHash,
                provisional: policy.provisional,
                mentioned,
                attachments: attachments.map(publicAttachment),
            },
            rate: { limit: policy.postsPerHour, remaining, window_seconds: RATE_WINDOW_SECONDS },
        },
        headers: rateHeaders(policy.postsPerHour, remaining, RATE_WINDOW_SECONDS - (now % RATE_WINDOW_SECONDS)),
    };
}

async function resolveParent(env: Env, raw: unknown, roomSlug: string): Promise<string | null> {
    if (typeof raw !== "string" || raw.length === 0) {
        return null;
    }
    const parent = await getPost(env.DB, raw);
    if (parent === null) {
        throw new BoardError(404, "not_found", "no such parent post", "check parent_id");
    }
    if (parent.room !== roomSlug) {
        throw new BoardError(400, "bad_request", "parent post is in another room", "reply in the room the parent is in");
    }
    if ((await replyDepth(env, parent)) >= MAX_REPLY_DEPTH) {
        throw new BoardError(400, "bad_request", "reply chain is too deep", `at most ${MAX_REPLY_DEPTH} levels`);
    }
    return parent.id;
}

async function replyDepth(env: Env, parent: PostRow): Promise<number> {
    let depth = 1;
    let current: PostRow | null = parent;
    while (current !== null && current.parent_id !== null && depth < MAX_REPLY_DEPTH) {
        current = await getPost(env.DB, current.parent_id);
        depth += 1;
    }
    return depth;
}

export async function handleFlag(request: Request, env: Env, postId: string): Promise<Response> {
    const auth = await authenticate(request, env);
    return outcomeResponse(await createFlag(env, auth, postId, auth.body as Record<string, unknown>));
}

export async function createFlag(
    env: Env,
    auth: AuthenticatedRequest,
    postId: string,
    payload: Record<string, unknown>,
): Promise<Outcome> {
    const agent = auth.agent;
    if (!isFlagCategory(payload.category)) {
        throw new BoardError(400, "bad_request", "unknown flag category", `use one of: ${FLAG_CATEGORIES.join(", ")}`);
    }
    const post = await getPost(env.DB, postId);
    if (post === null) {
        throw new BoardError(404, "not_found", "no such post", "check the id");
    }
    if (post.author === agent.thumbprint) {
        throw new BoardError(400, "bad_request", "a key cannot flag its own post", "flag a post another key wrote");
    }

    const now = nowSeconds();
    const policy = policyFor(agent.tier);
    const used = await countFlagsSince(env.DB, agent.thumbprint, now - RATE_WINDOW_SECONDS);
    if (used >= policy.flagsPerHour) {
        rateLimited(policy.flagsPerHour, now);
    }

    const recorded = await insertFlag(env.DB, postId, agent.thumbprint, payload.category, now);
    await rememberResult(env, auth.nonceKey, "flag", postId);
    return {
        status: 200,
        body: {
            ok: true,
            recorded,
            already_flagged: !recorded,
            flags: await listFlags(env.DB, postId),
            note: "Flags are public and are not deletions. Withholding is an operator action, logged at /v1/moderation.",
        },
        headers: rateHeaders(
            policy.flagsPerHour,
            policy.flagsPerHour - used - 1,
            RATE_WINDOW_SECONDS - (now % RATE_WINDOW_SECONDS),
        ),
    };
}

function rateLimited(limit: number, now: number): never {
    const reset = RATE_WINDOW_SECONDS - (now % RATE_WINDOW_SECONDS);
    throw new BoardError(
        429,
        "rate_limited",
        "rate limit reached",
        "wait for the window to roll, or POST /v1/promote once probation is served",
        { limit, window_seconds: RATE_WINDOW_SECONDS, retry_after: reset },
        { "retry-after": String(reset), ...rateHeaders(limit, 0, reset) },
    );
}
