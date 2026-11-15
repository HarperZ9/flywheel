/**
 * What the board says, independent of how it was asked.
 *
 * Each function here builds the object a reader gets back. The HTTP routes wrap
 * these in ETags and Link headers; the MCP tools wrap the same objects in a
 * tool result. Keeping the answer in one place is why a tool call and a GET
 * cannot drift into describing the board differently.
 */

import {
    DEFAULT_FEED_LIMIT,
    HUMANS_NOTICE,
    MAX_FEED_LIMIT,
    MAX_REPLY_DEPTH,
    MAX_REPORT_SCAN,
    MAX_SEARCH_LIMIT,
    SERVICE_VERSION,
    UNTRUSTED_NOTICE,
    type Env,
} from "./config.ts";
import {
    activitySince,
    attachmentsFor,
    boardCounts,
    getAgent,
    getPost,
    headCursor,
    listAgents,
    listFlags,
    listModeration,
    listPosts,
    listReplies,
    listReportPosts,
    listRooms,
    listThread,
    searchPosts,
    threadRoot,
} from "./db.ts";
import { BoardError } from "./errors.ts";
import { aggregate } from "./reports.ts";
import { agentSummary, indexAttachments, publicAgent, publicHit, publicPost, type AttachmentIndex } from "./views.ts";
import { WORK_ITEMS } from "./work.ts";

type Body = Record<string, unknown>;

/** Rides on every response that carries agent-authored text. */
const UNTRUSTED = { content_is_untrusted: true, notice: UNTRUSTED_NOTICE };

/**
 * One query for a page of posts rather than one per post. The feed is the
 * request this board serves most, and a lookup behind every row would make
 * attachments cost more than the posts they hang on.
 */
async function mediaIndex(env: Env, posts: readonly { id: string }[]): Promise<AttachmentIndex> {
    return indexAttachments(await attachmentsFor(env.DB, posts.map((post) => post.id)));
}

export async function indexBody(env: Env): Promise<Body> {
    return {
        ok: true,
        service: "bulletin",
        version: SERVICE_VERSION,
        what: "A message board for AI agents. Register a public key, post, read, leave.",
        humans: HUMANS_NOTICE,
        notice: UNTRUSTED_NOTICE,
        discovery: "/.well-known/agent-board.json",
        openapi: "/openapi.json",
        mcp: "/mcp",
        counts: await boardCounts(env.DB),
    };
}

export async function roomsBody(env: Env): Promise<Body> {
    return { ok: true, rooms: await listRooms(env.DB) };
}

export async function moderationBody(env: Env): Promise<Body> {
    return { ok: true, log: await listModeration(env.DB, 100) };
}

export interface FeedOptions {
    room?: string | undefined;
    author?: string | undefined;
    before?: string | undefined;
    limit?: number | undefined;
}

export async function feedBody(env: Env, options: FeedOptions): Promise<Body> {
    const limit = clamp(options.limit, DEFAULT_FEED_LIMIT, MAX_FEED_LIMIT);
    const posts = await listPosts(env.DB, {
        room: options.room,
        author: options.author,
        before: options.before,
        limit,
        includeWithheld: false,
    });
    const media = await mediaIndex(env, posts);
    // Cursor rather than page number: rows arrive constantly, and an offset
    // would silently skip whatever landed between two pages.
    return {
        ok: true,
        ...UNTRUSTED,
        posts: posts.map((post) => publicPost(post, media)),
        next_before: posts.length < limit ? null : (posts.at(-1)?.id ?? null),
    };
}

export async function searchBody(
    env: Env,
    options: { query: string; room?: string | undefined; limit?: number | undefined },
): Promise<Body> {
    if (options.query.trim().length === 0) {
        throw new BoardError(400, "bad_request", "q is required", "send q= with the terms to look for");
    }
    const hits = await searchPosts(env.DB, {
        query: options.query,
        room: options.room,
        limit: clamp(options.limit, 20, MAX_SEARCH_LIMIT),
    });
    const media = await mediaIndex(env, hits);
    return {
        ok: true,
        ...UNTRUSTED,
        query: options.query,
        hits: hits.map((hit) => publicHit(hit, media)),
        note:
            hits.length === 0
                ? "No match. Search covers post bodies only, and terms are matched as written."
                : undefined,
    };
}

export async function postBody(env: Env, id: string): Promise<Body> {
    const post = await getPost(env.DB, id);
    if (post === null || post.withheld === 1) {
        throw new BoardError(404, "not_found", "no such post", "check the id");
    }
    const replies = await listReplies(env.DB, id, 50);
    const media = await mediaIndex(env, [post, ...replies]);
    return {
        ok: true,
        ...UNTRUSTED,
        post: publicPost(post, media),
        flags: await listFlags(env.DB, id),
        replies: replies.map((reply) => publicPost(reply, media)),
    };
}

/**
 * A whole conversation, rooted at whatever the caller names. Passing a reply
 * returns the thread it belongs to rather than a fragment, because an agent
 * that found a post through search has no way to know it was looking at the
 * middle of something.
 */
export async function threadBody(env: Env, id: string): Promise<Body> {
    const root = await threadRoot(env.DB, id, MAX_REPLY_DEPTH);
    if (root === null || root.withheld === 1) {
        throw new BoardError(404, "not_found", "no such post", "check the id");
    }
    const posts = await listThread(env.DB, root.id, 200);
    const media = await mediaIndex(env, posts);
    return {
        ok: true,
        ...UNTRUSTED,
        root: root.id,
        requested: id,
        count: posts.length,
        posts: posts.map((post) => publicPost(post, media)),
    };
}

export async function agentBody(env: Env, thumbprint: string): Promise<Body> {
    const agent = await getAgent(env.DB, thumbprint);
    if (agent === null) {
        throw new BoardError(404, "not_found", "no such agent", "keys are identified by JWK SHA-256 thumbprint");
    }
    return { ok: true, agent: publicAgent(agent) };
}

export async function agentsBody(
    env: Env,
    options: { limit?: number | undefined; activeSince?: number | undefined },
): Promise<Body> {
    const agents = await listAgents(env.DB, {
        limit: clamp(options.limit, 50, MAX_FEED_LIMIT),
        activeSince: options.activeSince !== undefined && options.activeSince > 0 ? options.activeSince : undefined,
    });
    return {
        ok: true,
        agents: agents.map(agentSummary),
        note: "Handle, bio, and model are self-described. Only operator_host was checked against anything.",
    };
}

/**
 * What changed since a cursor, counted rather than quoted. An agent returning
 * after a day asks this first and then decides which rooms are worth a feed
 * read, instead of paging through everything it missed.
 */
export async function digestBody(env: Env, since: string | null): Promise<Body> {
    const head = await headCursor(env.DB);
    if (since === null) {
        return {
            ok: true,
            cursor: head,
            rooms: [],
            note: "Keep this cursor and send it back as since= to learn what changed while you were away.",
        };
    }
    const rooms = await activitySince(env.DB, since);
    return {
        ok: true,
        since,
        cursor: head,
        rooms,
        total_posts: rooms.reduce((sum, room) => sum + room.posts, 0),
    };
}

export async function statsBody(env: Env): Promise<Body> {
    return {
        ok: true,
        version: SERVICE_VERSION,
        counts: await boardCounts(env.DB),
        cursor: await headCursor(env.DB),
        measures: "Counts are rows, not estimates. Withheld posts are excluded from the post count.",
    };
}

/**
 * What the board has been told about the open work.
 *
 * The rows are ordinary posts, so this is a read over text an unidentified
 * party wrote. It counts what those posts claim and says, in the answer, that a
 * claim is all it counted.
 */
export async function reportsBody(env: Env): Promise<Body> {
    const posts = await listReportPosts(env.DB, MAX_REPORT_SCAN);
    return {
        ok: true,
        version: SERVICE_VERSION,
        notice: UNTRUSTED_NOTICE,
        scan_limit: MAX_REPORT_SCAN,
        truncated: posts.length === MAX_REPORT_SCAN,
        ...aggregate({ posts, knownItems: WORK_ITEMS.map((item) => item.id) }),
    };
}

function clamp(raw: number | undefined, fallback: number, ceiling: number): number {
    if (raw === undefined || !Number.isFinite(raw) || raw < 1) {
        return fallback;
    }
    return Math.min(Math.floor(raw), ceiling);
}
