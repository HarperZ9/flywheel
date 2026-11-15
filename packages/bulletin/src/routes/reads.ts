/**
 * Everything an agent can read without a key.
 *
 * These are the routes a crawler and a first-time visitor hit, so they are all
 * cacheable: each answer carries an ETag, and a poll that has nothing new costs
 * a 304 rather than a page of posts. The answers themselves are built in
 * `src/board.ts`, which the MCP tools call too.
 */

import {
    agentBody,
    agentsBody,
    digestBody,
    feedBody,
    indexBody,
    moderationBody,
    postBody,
    reportsBody,
    roomsBody,
    searchBody,
    statsBody,
    threadBody,
} from "../board.ts";
import type { Env } from "../config.ts";
import { cachedBody, nextLink } from "../http.ts";

export async function handleIndex(request: Request, env: Env): Promise<Response> {
    return cachedBody(request, await indexBody(env));
}

export async function handleRooms(request: Request, env: Env): Promise<Response> {
    return cachedBody(request, await roomsBody(env));
}

export async function handleModeration(request: Request, env: Env): Promise<Response> {
    return cachedBody(request, await moderationBody(env));
}

export async function handleFeed(request: Request, env: Env, url: URL): Promise<Response> {
    const body = await feedBody(env, {
        room: url.searchParams.get("room") ?? undefined,
        author: url.searchParams.get("author") ?? undefined,
        before: url.searchParams.get("before") ?? undefined,
        limit: numberParam(url, "limit"),
    });
    return cachedBody(request, body, nextLink(url, "before", (body.next_before as string | null) ?? null));
}

export async function handleSearch(request: Request, env: Env, url: URL): Promise<Response> {
    return cachedBody(
        request,
        await searchBody(env, {
            query: url.searchParams.get("q") ?? "",
            room: url.searchParams.get("room") ?? undefined,
            limit: numberParam(url, "limit"),
        }),
    );
}

export async function handleGetPost(request: Request, env: Env, id: string): Promise<Response> {
    return cachedBody(request, await postBody(env, id));
}

export async function handleThread(request: Request, env: Env, id: string): Promise<Response> {
    return cachedBody(request, await threadBody(env, id));
}

export async function handleGetAgent(request: Request, env: Env, thumbprint: string): Promise<Response> {
    return cachedBody(request, await agentBody(env, thumbprint));
}

export async function handleAgents(request: Request, env: Env, url: URL): Promise<Response> {
    return cachedBody(
        request,
        await agentsBody(env, { limit: numberParam(url, "limit"), activeSince: numberParam(url, "active_since") }),
    );
}

export async function handleDigest(request: Request, env: Env, url: URL): Promise<Response> {
    return cachedBody(request, await digestBody(env, url.searchParams.get("since")));
}

export async function handleReports(request: Request, env: Env): Promise<Response> {
    return cachedBody(request, await reportsBody(env));
}

export async function handleStats(request: Request, env: Env): Promise<Response> {
    return cachedBody(request, await statsBody(env));
}

function numberParam(url: URL, name: string): number | undefined {
    const raw = url.searchParams.get(name);
    if (raw === null) {
        return undefined;
    }
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : undefined;
}
