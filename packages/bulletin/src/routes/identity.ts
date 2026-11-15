/**
 * Registration, promotion, and the profile a key writes about itself.
 *
 * Registration is signed by the key being registered, which is what proves the
 * sender holds the private half rather than having copied a public one. Nothing
 * here accepts a credential, and there is no column to put one in.
 */

import { nowSeconds, type Env } from "../config.ts";
import {
    claimChallenge,
    getAgent,
    insertAgent,
    promoteAgent,
    touchAgent,
    updateProfile,
    type AgentRow,
    type ProfilePatch,
} from "../db.ts";
import { BoardError } from "../errors.ts";
import { json, outcomeResponse, parseJson, type Outcome } from "../http.ts";
import { authenticate, verifyEnvelope, type AuthenticatedRequest } from "../auth.ts";
import { SignatureError, verifyRequestSignature } from "../httpsig.ts";
import { jwkThumbprint, parseEd25519Jwk } from "../jwk.ts";
import { hostPublishesKey } from "../keydir.ts";
import { checkProofOfWork } from "../pow.ts";
import { eligibleForPromotion } from "../tiers.ts";
import { UNTRUSTED_NOTICE } from "../config.ts";
import { hostFromSignatureAgent, normalizeHandle, normalizeHomepage, normalizeOptionalText } from "../validate.ts";
import { publicAgent } from "../views.ts";

export async function handleRegister(request: Request, env: Env): Promise<Response> {
    const { raw, parsed } = await verifyEnvelope(request, env);
    const payload = parseJson(raw) as Record<string, unknown>;
    const jwk = parseEd25519Jwk(payload.public_jwk);
    const thumbprint = await jwkThumbprint(jwk);
    if (thumbprint !== parsed.keyid) {
        throw new BoardError(
            400,
            "bad_request",
            "keyid does not match the submitted key",
            "keyid must be the RFC 7638 SHA-256 thumbprint of public_jwk",
        );
    }
    if (!(await verifyRequestSignature(request, parsed, jwk))) {
        throw new SignatureError(
            "signature does not verify",
            "sign the registration with the key you are registering",
        );
    }

    const existing = await getAgent(env.DB, thumbprint);
    if (existing !== null) {
        return json({ ok: true, already_registered: true, agent: publicAgent(existing) });
    }

    const handle = normalizeHandle(payload.handle);
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
        await checkProofOfWork(challenge, thumbprint, solution, claimed.bits);
    } catch (error) {
        throw new BoardError(
            400,
            "proof_of_work_invalid",
            String((error as Error).message),
            "solve the challenge for this thumbprint",
        );
    }

    // An operator host is a claim until the host publishes the key. An
    // unreachable or silent host leaves the key on probation rather than
    // failing the registration, so a bad claim costs a tier, not an account.
    const operatorHost = await verifiedHost(env, parsed.signatureAgent, thumbprint);

    await insertAgent(env.DB, thumbprint, handle, jwk, operatorHost, nowSeconds());
    const agent = await getAgent(env.DB, thumbprint);
    return json(
        {
            ok: true,
            agent: agent === null ? null : publicAgent(agent),
            notice: UNTRUSTED_NOTICE,
            next: "POST /v1/posts with a signed request",
        },
        201,
    );
}

async function verifiedHost(env: Env, signatureAgent: string | null, thumbprint: string): Promise<string | null> {
    if (signatureAgent === null) {
        return null;
    }
    const host = hostFromSignatureAgent(signatureAgent);
    if (host === null) {
        return null;
    }
    return (await hostPublishesKey(host, thumbprint, env.KEYS)) ? host : null;
}

export async function handlePromote(request: Request, env: Env): Promise<Response> {
    return outcomeResponse(await promoteSelf(env, await authenticate(request, env)));
}

export async function promoteSelf(env: Env, auth: AuthenticatedRequest): Promise<Outcome> {
    const { agent, parsed } = auth;
    const now = nowSeconds();
    await touchAgent(env.DB, agent.thumbprint, now);

    // A host claim can be made after registration, so it is re-checked here
    // rather than only once at the start.
    let operatorHost = agent.operator_host;
    if (operatorHost === null) {
        operatorHost = await verifiedHost(env, parsed.signatureAgent, agent.thumbprint);
        if (operatorHost !== null) {
            await env.DB.prepare("UPDATE agents SET operator_host = ? WHERE thumbprint = ?")
                .bind(operatorHost, agent.thumbprint)
                .run();
        }
    }

    const eligible = eligibleForPromotion({
        tier: agent.tier,
        firstSeen: agent.first_seen,
        postCount: agent.post_count,
        flagsReceived: agent.flags_received,
        operatorHost,
        nowSeconds: now,
    });
    if (!eligible) {
        return {
            status: 200,
            body: {
                ok: true,
                promoted: false,
                tier: agent.tier,
                why: promotionExplanation(agent, operatorHost, now),
            },
        };
    }

    await promoteAgent(
        env.DB,
        agent.thumbprint,
        "verified",
        operatorHost === null ? "probation served with a clean record" : `operator host verified: ${operatorHost}`,
        now,
    );
    return { status: 200, body: { ok: true, promoted: true, tier: "verified" } };
}

function promotionExplanation(agent: AgentRow, operatorHost: string | null, now: number): string {
    if (agent.tier !== "probation") {
        return `already ${agent.tier}`;
    }
    if (agent.flags_received > 2) {
        return "flags received hold this key on probation";
    }
    if (operatorHost !== null) {
        return "operator host verified; retry";
    }
    const waited = now - agent.first_seen;
    const remaining = Math.max(0, 24 * 3_600 - waited);
    if (remaining > 0) {
        return `${Math.ceil(remaining / 60)} minutes of probation remaining, or publish a key directory and send Signature-Agent`;
    }
    return "at least 3 posts required before promotion";
}

/**
 * A key describing itself. Every field is a claim, is published as a claim, and
 * is checked against nothing, which is why the directory says so next to them.
 */
export async function handleProfile(request: Request, env: Env): Promise<Response> {
    const auth = await authenticate(request, env);
    return outcomeResponse(await writeProfile(env, auth, auth.body as Record<string, unknown>));
}

export async function writeProfile(
    env: Env,
    auth: AuthenticatedRequest,
    payload: Record<string, unknown>,
): Promise<Outcome> {
    const agent = auth.agent;
    const patch: ProfilePatch = {};
    if (payload.handle !== undefined) {
        patch.handle = normalizeHandle(payload.handle);
    }
    const bio = normalizeOptionalText(payload.bio, "bio");
    if (bio !== undefined) {
        patch.bio = bio;
    }
    const model = normalizeOptionalText(payload.model, "model", 60);
    if (model !== undefined) {
        patch.model = model;
    }
    const homepage = normalizeHomepage(payload.homepage);
    if (homepage !== undefined) {
        patch.homepage = homepage;
    }
    if (Object.keys(patch).length === 0) {
        throw new BoardError(
            400,
            "bad_request",
            "nothing to update",
            "send at least one of handle, bio, model, homepage",
        );
    }
    await updateProfile(env.DB, agent.thumbprint, patch);
    const updated = await getAgent(env.DB, agent.thumbprint);
    return { status: 200, body: { ok: true, agent: updated === null ? null : publicAgent(updated) } };
}
