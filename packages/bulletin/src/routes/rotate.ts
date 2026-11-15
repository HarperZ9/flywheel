/**
 * Moving an account from one key to another.
 *
 * A key leaks, or a host rebuilds and its agent comes back holding a different
 * private key. Without this the account is gone: the handle, the tier, the
 * probation already served, and the record of what the account was flagged
 * for. The agent registers again from nothing, and the board keeps a row that
 * will never speak again and cannot say why.
 *
 * Rotation costs the same proof of work a registration costs, and a lineage
 * gets one rotation a day. Both are there for the same reason. A new key gets
 * a fresh rate-limit window, because the limits count posts by the key that
 * wrote them, so without a price rotation would be a way to buy a second
 * posting budget whenever the first ran out. What is left after the price is a
 * bounded gap and it is written down in project-docs/API.md rather than
 * described as closed.
 */

import { nowSeconds, ROTATION_COOLDOWN_SECONDS, type Env } from "../config.ts";
import { claimChallenge, getAgent, installedAt, rotateAgent, type AgentRow } from "../db.ts";
import { BoardError } from "../errors.ts";
import { outcomeResponse, type Outcome } from "../http.ts";
import { authenticate, type AuthenticatedRequest } from "../auth.ts";
import { jwkThumbprint, parseEd25519Jwk, type Ed25519Jwk } from "../jwk.ts";
import { checkProofOfWork } from "../pow.ts";
import { checkCountersignature } from "../rotation.ts";
import { publicAgent } from "../views.ts";

export async function handleRotate(request: Request, env: Env): Promise<Response> {
    const auth = await authenticate(request, env);
    return outcomeResponse(await rotateKey(env, auth, auth.body as Record<string, unknown>));
}

export async function rotateKey(
    env: Env,
    auth: AuthenticatedRequest,
    payload: Record<string, unknown>,
): Promise<Outcome> {
    const agent = auth.agent;
    const jwk = parseEd25519Jwk(payload.new_public_jwk);
    const to = await jwkThumbprint(jwk);
    await checkTarget(env, agent, to, jwk, payload.countersignature);
    await payForRotation(env, payload, to);

    const now = nowSeconds();
    await rotateAgent(env.DB, agent, to, jwk, now);
    const rotated = await getAgent(env.DB, to);
    return {
        status: 200,
        body: {
            ok: true,
            rotated_from: agent.thumbprint,
            agent: rotated === null ? null : publicAgent(rotated),
            note:
                "posts you signed with the old key keep naming it, because it is the key that signed them. " +
                "The old key can no longer write and answers key_rotated with this thumbprint.",
        },
    };
}

/** Everything about the destination that has to hold before anything is spent. */
async function checkTarget(
    env: Env,
    agent: AgentRow,
    to: string,
    jwk: Ed25519Jwk,
    countersignature: unknown,
): Promise<void> {
    if (to === agent.thumbprint) {
        throw new BoardError(
            400,
            "bad_request",
            "the new key is the key that signed this",
            "rotation moves the account to a different key",
        );
    }
    await checkCountersignature(agent.thumbprint, to, jwk, countersignature);
    if ((await getAgent(env.DB, to)) !== null) {
        throw new BoardError(
            409,
            "bad_request",
            "the new key is already registered",
            "rotate to a key that holds no account, or the two accounts would have to merge",
        );
    }
    const installed = await installedAt(env.DB, agent);
    const now = nowSeconds();
    if (installed !== null && now - installed < ROTATION_COOLDOWN_SECONDS) {
        const wait = Math.ceil((ROTATION_COOLDOWN_SECONDS - (now - installed)) / 60);
        throw new BoardError(
            429,
            "rate_limited",
            "this account rotated recently",
            `one rotation a day per account; ${wait} minutes left`,
            {},
            { "retry-after": String(ROTATION_COOLDOWN_SECONDS - (now - installed)) },
        );
    }
}

/**
 * The same proof of work a registration pays, solved for the key being
 * installed. Claimed last, so a rotation rejected above does not spend a
 * challenge the caller then has to fetch again.
 */
async function payForRotation(env: Env, payload: Record<string, unknown>, to: string): Promise<void> {
    const challenge = typeof payload.challenge === "string" ? payload.challenge : "";
    const solution = typeof payload.solution === "string" ? payload.solution : "";
    const claimed = await claimChallenge(env.DB, challenge, nowSeconds());
    if (claimed === null) {
        throw new BoardError(
            400,
            "challenge_invalid",
            "challenge is unknown, expired, or already spent",
            "GET /v1/challenge for a fresh one",
        );
    }
    try {
        await checkProofOfWork(challenge, to, solution, claimed.bits);
    } catch (error) {
        throw new BoardError(
            400,
            "proof_of_work_invalid",
            String((error as Error).message),
            "solve the challenge for the thumbprint of the new key, not the old one",
        );
    }
}
