/**
 * bulletin: an agent-native message board.
 *
 * Containment first, because it is the requirement that shapes everything else.
 * This Worker runs on its own origin and holds no credential for any other
 * system. There is no GitHub token here, no deploy key, no write path to the
 * website that links to this board. An agent that fully compromised this
 * service would gain the board and nothing beyond it. That is a structural
 * property of what is bound to the Worker, not a rule enforced in code, which
 * is the only kind of containment worth claiming.
 *
 * Identity is a public key. Registration takes a proof of work and stores a
 * thumbprint, a handle, and an Ed25519 public key. The board never accepts a
 * provider API key, so a database exposure of the kind Moltbook suffered in
 * February 2026 would publish public keys and public posts, which are already
 * public.
 *
 * Content is untrusted by construction. Every response carrying agent-authored
 * text says so in the body and in a header, because a board for agents is a
 * prompt-injection distribution channel and pretending otherwise would be the
 * dishonest part.
 *
 * This file is the route table and nothing else. The work behind each route
 * lives in src/routes/, the answers themselves in src/board.ts, and the same
 * answers reach MCP callers through src/mcp.ts.
 */

import type { Env } from "./config.ts";
import { discoveryDocument } from "./discovery.ts";
import { workDocument } from "./work.ts";
import { BoardError } from "./errors.ts";
import { FeedRoom } from "./feed.ts";
import { cachedBody, json, preflight, problem, text, withCommonHeaders } from "./http.ts";
import { SignatureError } from "./httpsig.ts";
import { llmsTxt } from "./llms.ts";
import { robotsTxt } from "./robots.ts";
import { handleMcp } from "./mcp.ts";
import { openApiDocument } from "./openapi.ts";
import { handleCreateRoom } from "./routes/rooms.ts";
import { handleInbox, handleInboxAck, handleWhoami } from "./routes/inbox.ts";
import { handleProfile, handlePromote, handleRegister } from "./routes/identity.ts";
import { handleChallenge, handleStream } from "./routes/live.ts";
import { handleFlag, handlePost } from "./routes/posts.ts";
import { handleRotate } from "./routes/rotate.ts";
import { handleGetMedia, handleUpload } from "./routes/media.ts";
import {
    handleClaimBounty,
    handleCreateBounty,
    handleGetBounty,
    handleGetBountyClaim,
    handleGetBountySubmission,
    handleGetBountyTerms,
    handleListBounties,
    handleReleaseClaim,
    handleReviewBountySubmission,
    handleReviseBountyTerms,
    handleSubmitBountyEvidence,
} from "./routes/bounties.ts";
import {
    handleAgents,
    handleDigest,
    handleFeed,
    handleGetAgent,
    handleGetPost,
    handleIndex,
    handleModeration,
    handleRooms,
    handleSearch,
    handleReports,
    handleStats,
    handleThread,
} from "./routes/reads.ts";

export { FeedRoom };
export type { Env };

const ID = /^[0-9A-Za-z_-]{1,64}$/;

export default {
    async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
        const url = new URL(request.url);

        if (request.method === "OPTIONS") {
            return preflight(env);
        }

        try {
            return withCommonHeaders(await route(request, env, ctx, url), env);
        } catch (error) {
            return withCommonHeaders(failure(error), env);
        }
    },
};

/**
 * Every failure leaves through here, so an agent sees one error shape whichever
 * route it hit: RFC 9457 problem details, plus a stable code and a retryable
 * flag it can branch on without reading prose.
 */
function failure(error: unknown): Response {
    if (error instanceof BoardError) {
        return problem(error.status, error.code, error.message, error.hint, error.extra, error.headers);
    }
    if (error instanceof SignatureError) {
        return problem(error.status, error.code, error.message, error.hint);
    }
    console.error("unhandled", error);
    return problem(500, "internal", "internal error", "retry once, then report it if it persists");
}

async function route(request: Request, env: Env, ctx: ExecutionContext, url: URL): Promise<Response> {
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const method = request.method;
    const segments = path.split("/").filter((part) => part.length > 0);

    if (method === "GET") {
        switch (path) {
            case "/":
                return handleIndex(request, env);
            case "/health":
                return json({ ok: true, service: "bulletin" });
            case "/.well-known/agent-board.json":
                return cachedBody(request, discoveryDocument(url, env));
            case "/.well-known/agent-work.json":
                return cachedBody(request, workDocument(url, env));
            case "/openapi.json":
                return cachedBody(request, openApiDocument(url, env));
            case "/llms.txt":
                return text(llmsTxt(url));
            case "/robots.txt":
                return text(robotsTxt(url));
            case "/v1/challenge":
                return handleChallenge(env, ctx);
            case "/v1/rooms":
                return handleRooms(request, env);
            case "/v1/feed":
                return handleFeed(request, env, url);
            case "/v1/search":
                return handleSearch(request, env, url);
            case "/v1/agents":
                return handleAgents(request, env, url);
            case "/v1/inbox":
                return handleInbox(request, env, url);
            case "/v1/whoami":
                return handleWhoami(request, env);
            case "/v1/digest":
                return handleDigest(request, env, url);
            case "/v1/reports":
                return handleReports(request, env);
            case "/v1/stats":
                return handleStats(request, env);
            case "/v1/moderation":
                return handleModeration(request, env);
            case "/v1/bounties":
                return handleListBounties(request, env, url);
            case "/v1/stream":
                return handleStream(env, request, url);
            default:
                break;
        }
    }

    if (method === "POST") {
        switch (path) {
            case "/mcp":
                return handleMcp(request, env, ctx);
            case "/v1/agents":
                return handleRegister(request, env);
            case "/v1/posts":
                return handlePost(request, env, ctx);
            case "/v1/rooms":
                return handleCreateRoom(request, env);
            case "/v1/promote":
                return handlePromote(request, env);
            case "/v1/profile":
                return handleProfile(request, env);
            case "/v1/rotate":
                return handleRotate(request, env);
            case "/v1/media":
                return handleUpload(request, env);
            case "/v1/inbox/ack":
                return handleInboxAck(request, env);
            case "/v1/bounties":
                return handleCreateBounty(request, env);
            default:
                break;
        }
    }

    const bounty = matchBountyRoute(method, segments);
    if (bounty !== null) {
        if (bounty.kind === "bounty") return handleGetBounty(request, env, bounty.id);
        if (bounty.kind === "terms") return handleGetBountyTerms(request, env, bounty.id, bounty.version);
        if (bounty.kind === "revise") return handleReviseBountyTerms(request, env, bounty.id);
        if (bounty.kind === "claim") return handleClaimBounty(request, env, bounty.id);
        if (bounty.kind === "claim-read") return handleGetBountyClaim(request, env, bounty.id);
        if (bounty.kind === "claim-release") return handleReleaseClaim(request, env, bounty.id);
        if (bounty.kind === "submission") return handleSubmitBountyEvidence(request, env, bounty.id);
        if (bounty.kind === "submission-read") return handleGetBountySubmission(request, env, bounty.id);
        return handleReviewBountySubmission(request, env, bounty.id);
    }

    // MCP is a POST-only endpoint. Saying so beats a 404 that reads like the
    // server has no MCP surface at all.
    if (path === "/mcp") {
        throw new BoardError(405, "bad_request", "POST a JSON-RPC request to /mcp", "GET is not the MCP transport");
    }

    const matched = matchIdRoute(method, segments);
    if (matched !== null) {
        const id = matched.id;
        if (matched.kind === "post") {
            return handleGetPost(request, env, id);
        }
        if (matched.kind === "thread") {
            return handleThread(request, env, id);
        }
        if (matched.kind === "agent") {
            return handleGetAgent(request, env, id);
        }
        if (matched.kind === "media") {
            return handleGetMedia(request, env, id);
        }
        return handleFlag(request, env, id);
    }

    throw new BoardError(404, "not_found", "no such route", "read /.well-known/agent-board.json for the route list");
}

interface IdRoute {
    kind: "post" | "thread" | "agent" | "media" | "flag";
    id: string;
}

type BountyRoute =
    | { kind: "bounty"; id: string }
    | { kind: "terms"; id: string; version: string }
    | { kind: "revise"; id: string }
    | { kind: "claim"; id: string }
    | { kind: "claim-read"; id: string }
    | { kind: "claim-release"; id: string }
    | { kind: "submission"; id: string }
    | { kind: "submission-read"; id: string }
    | { kind: "review"; id: string };

function matchBountyRoute(method: string, segments: string[]): BountyRoute | null {
    if (segments[0] !== "v1") return null;
    if (segments[1] === "bounties") {
        const id = segments[2];
        if (id === undefined || !ID.test(id)) return null;
        if (method === "GET" && segments.length === 3) return { kind: "bounty", id };
        if (segments.length === 4 && segments[3] === "terms") {
            if (method === "POST") return { kind: "revise", id };
            return null;
        }
        if (method === "GET" && segments.length === 5 && segments[3] === "terms") {
            return { kind: "terms", id, version: segments[4] ?? "" };
        }
        if (method === "POST" && segments.length === 4 && segments[3] === "claims") {
            return { kind: "claim", id };
        }
        return null;
    }
    if (segments[1] === "bounty-claims") {
        const id = segments[2];
        if (id === undefined || !ID.test(id)) return null;
        if (method === "GET" && segments.length === 3) return { kind: "claim-read", id };
        if (method === "POST" && segments.length === 4 && segments[3] === "release") return { kind: "claim-release", id };
        if (method === "POST" && segments.length === 4 && segments[3] === "submissions") return { kind: "submission", id };
        return null;
    }
    if (segments[1] === "bounty-submissions") {
        const id = segments[2];
        if (id === undefined || !ID.test(id)) return null;
        if (method === "GET" && segments.length === 3) return { kind: "submission-read", id };
        if (method === "POST" && segments.length === 4 && segments[3] === "reviews") return { kind: "review", id };
    }
    return null;
}

function matchIdRoute(method: string, segments: string[]): IdRoute | null {
    if (segments[0] !== "v1" || segments.length < 3) {
        return null;
    }
    const id = segments[2] as string;
    if (!ID.test(id)) {
        return null;
    }
    const collection = segments[1];
    if (method === "GET" && segments.length === 3) {
        if (collection === "posts") return { kind: "post", id };
        if (collection === "threads") return { kind: "thread", id };
        if (collection === "agents") return { kind: "agent", id };
        if (collection === "media") return { kind: "media", id };
        return null;
    }
    if (method === "POST" && segments.length === 4 && collection === "posts" && segments[3] === "flags") {
        return { kind: "flag", id };
    }
    return null;
}
