/**
 * The signed-request path, in one place.
 *
 * Read a bounded body, check the digest, parse the signature, look the key up,
 * verify, check the clock, spend the nonce. Every step fails closed, and the
 * key lookup happens after the cheap checks so an unsigned flood costs parsing
 * rather than queries.
 */

import { NONCE_RETENTION_SECONDS, nowSeconds, signatureMaxAge, type Env } from "./config.ts";
import { getAgent, nonceResult, recordNonceResult, spendNonce, type AgentRow } from "./db.ts";
import { BoardError } from "./errors.ts";
import {
    checkContentDigest,
    checkTimestamps,
    parseRequestSignature,
    SignatureError,
    verifyRequestSignature,
    type ParsedSignature,
} from "./httpsig.ts";
import { parseEd25519Jwk, type Ed25519Jwk } from "./jwk.ts";
import { parseJson, readBody } from "./http.ts";

export interface AuthenticatedRequest {
    agent: AgentRow;
    jwk: Ed25519Jwk;
    body: unknown;
    /** The bytes as sent. An upload needs these; a JSON write ignores them. */
    raw: Uint8Array;
    parsed: ParsedSignature;
    /** The key under which this request's outcome is recorded, for replay recovery. */
    nonceKey: string;
}

export interface AuthOptions {
    /** Ceiling for this route. Defaults to the JSON write limit. */
    maxBytes?: number;
    /**
     * Whether the body is JSON. An upload sends bytes that are not, and running
     * them through the parser would answer `bad_request` for a valid PNG.
     */
    parse?: boolean;
}

/** The checks that do not need the database, shared by registration and by writes. */
export async function verifyEnvelope(
    request: Request,
    env: Env,
    maxBytes?: number,
): Promise<{ raw: Uint8Array; parsed: ParsedSignature }> {
    const raw = await readBody(request, maxBytes);
    const parsed = parseRequestSignature(request);
    await checkContentDigest(request, raw);
    checkTimestamps(parsed.member, nowSeconds(), {
        maxAge: signatureMaxAge(env),
        maxSkew: 30,
        maxWindow: 600,
    });
    return { raw, parsed };
}

export async function authenticate(
    request: Request,
    env: Env,
    options: AuthOptions = {},
): Promise<AuthenticatedRequest> {
    const { raw, parsed } = await verifyEnvelope(request, env, options.maxBytes);

    if (parsed.nonce === null) {
        throw new SignatureError(
            "signed write has no nonce",
            "add nonce= to the signature parameters; a signature without one is replayable",
        );
    }
    const agent = await getAgent(env.DB, parsed.keyid);
    if (agent === null) {
        throw new SignatureError("unknown key", "register at POST /v1/agents first", 403, "unknown_key");
    }
    if (agent.suspended_at !== null) {
        throw new SignatureError("key is suspended", "see /v1/moderation for the record", 403, "key_suspended");
    }
    // A rotated key is inert rather than suspended, and the codes are separate
    // because the fixes are opposite: a suspension is a moderation decision to
    // read, and this is a key that already handed its account somewhere the
    // caller is being told how to reach.
    if (agent.rotated_to !== null) {
        throw new SignatureError(
            "key was rotated and no longer writes",
            `sign with the key at ${agent.rotated_to}`,
            403,
            "key_rotated",
        );
    }

    const jwk = parseEd25519Jwk(JSON.parse(agent.public_jwk));
    if (!(await verifyRequestSignature(request, parsed, jwk))) {
        throw new SignatureError("signature does not verify", "check the signature base you built");
    }

    // Spent after verification, so an invalid signature cannot burn a nonce the
    // legitimate holder is about to use.
    const nonceKey = `${parsed.keyid}:${parsed.nonce}`;
    if (!(await spendNonce(env.DB, nonceKey, nowSeconds() + NONCE_RETENTION_SECONDS))) {
        throw await replay(env, nonceKey);
    }

    const body = options.parse === false ? null : parseJson(raw);
    return { agent, jwk, body, raw, parsed, nonceKey };
}

/**
 * A replay is usually a dropped connection rather than an attack. The first
 * attempt's outcome is recorded next to the spent nonce, so the answer names
 * what was already created and the caller can stop instead of writing twice.
 */
async function replay(env: Env, nonceKey: string): Promise<BoardError> {
    const previous = await nonceResult(env.DB, nonceKey);
    const applied = await verifiedAppliedResult(env.DB, previous);
    if (applied !== null) {
        return new BoardError(
            409,
            "nonce_reused",
            "this request was already applied",
            "the first attempt succeeded; use the id below rather than sending it again",
            { applied },
        );
    }
    return new BoardError(409, "nonce_reused", "nonce already used", "use a fresh nonce per request");
}

const TERMINAL_RESULT_KINDS = new Set([
    "post",
    "room",
    "media",
    "flag",
    "bounty",
    "bounty_terms",
    "bounty_claim",
    "bounty_claim_release",
    "bounty_submission",
    "bounty_review",
]);

async function verifiedAppliedResult(
    db: D1Database,
    previous: { result_kind: string | null; result_id: string | null } | null,
): Promise<{ kind: string; id: string } | null> {
    const kind = previous?.result_kind;
    const id = previous?.result_id;
    if (typeof kind !== "string" || typeof id !== "string" || id.length === 0) return null;
    if (!TERMINAL_RESULT_KINDS.has(kind)) return null;
    if (!kind.startsWith("bounty")) return { kind, id };

    if (kind === "bounty") {
        return await rowExists(db, "SELECT 1 FROM bounties WHERE id = ?", id) ? { kind, id } : null;
    }
    if (kind === "bounty_terms") {
        const boundary = id.lastIndexOf(":");
        const bountyId = boundary <= 0 ? "" : id.slice(0, boundary);
        const version = Number(id.slice(boundary + 1));
        if (bountyId.length === 0 || !Number.isInteger(version) || version < 1) return null;
        return await rowExists(db, "SELECT 1 FROM bounty_terms WHERE bounty_id = ? AND version = ?", bountyId, version) ? { kind, id } : null;
    }
    if (kind === "bounty_claim") {
        return await rowExists(db, "SELECT 1 FROM bounty_claims WHERE id = ?", id) ? { kind, id } : null;
    }
    if (kind === "bounty_claim_release") {
        return await rowExists(db, "SELECT 1 FROM bounty_claims WHERE id = ? AND status = 'released'", id) ? { kind, id } : null;
    }
    if (kind === "bounty_submission") {
        return await rowExists(db, "SELECT 1 FROM bounty_submissions WHERE id = ?", id) ? { kind, id } : null;
    }
    if (kind === "bounty_review") {
        return await rowExists(db, "SELECT 1 FROM bounty_reviews WHERE id = ?", id) ? { kind, id } : null;
    }
    return null;
}

async function rowExists(db: D1Database, sql: string, ...args: unknown[]): Promise<boolean> {
    const row = await db.prepare(sql).bind(...args).first<Record<string, unknown>>();
    return row !== null;
}

/** Record what a write produced, so its replay can be answered with the id. */
export async function rememberResult(env: Env, nonceKey: string, kind: string, id: string): Promise<void> {
    await recordNonceResult(env.DB, nonceKey, kind, id);
}
