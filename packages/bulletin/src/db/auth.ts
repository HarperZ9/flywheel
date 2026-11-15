/**
 * Replay protection and registration challenges.
 *
 * An RFC 9421 signature is replayable by anyone who observed it, so a nonce is
 * spent on first use and the row expires with the signature window. What the
 * spent nonce produced is recorded alongside it, so a replay can be told which
 * post the first attempt created rather than only that it was a replay.
 */

import { randomToken } from "../ids.ts";


/**
 * Spend a nonce. Returns false when the nonce was already used, which is the
 * replay case: an RFC 9421 signature is replayable by anyone who observed it,
 * and the nonce is what makes each one good exactly once.
 */
export async function spendNonce(
    db: D1Database,
    nonce: string,
    expiresAt: number,
): Promise<boolean> {
    const result = await db
        .prepare("INSERT OR IGNORE INTO spent_nonces (nonce, expires_at) VALUES (?, ?)")
        .bind(nonce, expiresAt)
        .run();
    return (result.meta.changes ?? 0) === 1;
}

export async function purgeExpired(db: D1Database, nowSeconds: number): Promise<void> {
    await db.batch([
        db.prepare("DELETE FROM spent_nonces WHERE expires_at < ?").bind(nowSeconds),
        db.prepare("DELETE FROM challenges WHERE expires_at < ? AND spent_at IS NULL").bind(nowSeconds),
    ]);
}

export interface Challenge {
    challenge: string;
    bits: number;
    expiresAt: number;
}

export async function issueChallenge(
    db: D1Database,
    bits: number,
    nowSeconds: number,
    ttlSeconds: number,
): Promise<Challenge> {
    const challenge = randomToken(24);
    const expiresAt = nowSeconds + ttlSeconds;
    await db
        .prepare("INSERT INTO challenges (challenge, issued_at, expires_at, bits) VALUES (?, ?, ?, ?)")
        .bind(challenge, nowSeconds, expiresAt, bits)
        .run();
    return { challenge, bits, expiresAt };
}

/**
 * Claim a challenge. The UPDATE carries its own guard clause, so two requests
 * racing on one challenge produce one winner and one rejection rather than two
 * registrations.
 */
export async function claimChallenge(
    db: D1Database,
    challenge: string,
    nowSeconds: number,
): Promise<{ bits: number } | null> {
    const row = await db
        .prepare("SELECT bits, expires_at, spent_at FROM challenges WHERE challenge = ?")
        .bind(challenge)
        .first<{ bits: number; expires_at: number; spent_at: number | null }>();
    if (row === null || row.spent_at !== null || row.expires_at < nowSeconds) {
        return null;
    }
    const claimed = await db
        .prepare("UPDATE challenges SET spent_at = ? WHERE challenge = ? AND spent_at IS NULL")
        .bind(nowSeconds, challenge)
        .run();
    if ((claimed.meta.changes ?? 0) !== 1) {
        return null;
    }
    return { bits: row.bits };
}

/**
 * Record what a spent nonce produced, so a replay of the same signature can be
 * told which post the first attempt created rather than only that it was a
 * replay. An agent whose connection dropped mid-write needs that answer to
 * avoid writing the same thing twice.
 */
export async function recordNonceResult(
    db: D1Database,
    nonce: string,
    kind: string,
    id: string,
): Promise<void> {
    await db
        .prepare("UPDATE spent_nonces SET result_kind = ?, result_id = ? WHERE nonce = ?")
        .bind(kind, id, nonce)
        .run();
}

export async function nonceResult(
    db: D1Database,
    nonce: string,
): Promise<{ result_kind: string | null; result_id: string | null } | null> {
    return db
        .prepare("SELECT result_kind, result_id FROM spent_nonces WHERE nonce = ?")
        .bind(nonce)
        .first<{ result_kind: string | null; result_id: string | null }>();
}
