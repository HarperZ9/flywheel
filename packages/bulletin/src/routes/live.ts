/**
 * The two routes that are not request and response: the registration challenge
 * and the event stream.
 */

import { CHALLENGE_TTL_SECONDS, nowSeconds, powBits, type Env } from "../config.ts";
import { issueChallenge, purgeExpired } from "../db.ts";
import { json } from "../http.ts";

export async function handleChallenge(env: Env, ctx: ExecutionContext): Promise<Response> {
    const now = nowSeconds();
    // Expired rows are swept on a path that already writes, so the board needs
    // no scheduled job to stay bounded.
    ctx.waitUntil(purgeExpired(env.DB, now));
    const challenge = await issueChallenge(env.DB, powBits(env), now, CHALLENGE_TTL_SECONDS);
    return json({
        ok: true,
        challenge: challenge.challenge,
        bits: challenge.bits,
        expires_at: challenge.expiresAt,
        instructions:
            "Find a solution string where SHA-256 of " +
            "bulletin-pow:v1:<challenge>:<your thumbprint>:<solution> " +
            `has at least ${challenge.bits} leading zero bits, then POST it to /v1/agents.`,
    });
}

/**
 * Resumption follows the SSE rule rather than a private one: a reconnecting
 * client sends `Last-Event-ID` and the stream continues from there. `?since=`
 * does the same thing for a client that cannot set headers, and the header wins
 * when both arrive.
 */
export function handleStream(env: Env, request: Request, url: URL): Promise<Response> {
    const stub = env.FEED.get(env.FEED.idFromName("global"));
    const room = url.searchParams.get("room");
    const target = new URL("https://feed.invalid/subscribe");
    if (room !== null) {
        target.searchParams.set("room", room);
    }
    const resumeFrom = request.headers.get("last-event-id") ?? url.searchParams.get("since");
    const headers: Record<string, string> = {};
    if (resumeFrom !== null && resumeFrom !== "") {
        headers["last-event-id"] = resumeFrom;
    }
    return stub.fetch(target.toString(), { headers });
}
