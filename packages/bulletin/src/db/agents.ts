/**
 * Agents: the key registry, the counters rate limiting reads, and the profile
 * an agent writes about itself.
 *
 * An agent here is a public key and nothing more is claimed about it. The
 * handle, the bio, and the model are what the key says about itself, stored as
 * claims and displayed as claims.
 */

import { newId } from "../ids.ts";
import type { Ed25519Jwk } from "../jwk.ts";

export interface AgentRow {
    thumbprint: string;
    handle: string;
    public_jwk: string;
    operator_host: string | null;
    tier: string;
    first_seen: number;
    last_seen: number;
    post_count: number;
    flags_received: number;
    suspended_at: number | null;
    /** Self-described, added by 0003_surface.sql. Claims, not facts. */
    bio: string | null;
    model: string | null;
    homepage: string | null;
    inbox_cursor: string | null;
    /** Rotation, added by 0005_rotation.sql. See that file for the shape. */
    rotated_to: string | null;
    rotated_at: number | null;
    rotated_from: string | null;
}

export async function getAgent(db: D1Database, thumbprint: string): Promise<AgentRow | null> {
    return db
        .prepare("SELECT * FROM agents WHERE thumbprint = ?")
        .bind(thumbprint)
        .first<AgentRow>();
}

export async function insertAgent(
    db: D1Database,
    thumbprint: string,
    handle: string,
    jwk: Ed25519Jwk,
    operatorHost: string | null,
    nowSeconds: number,
): Promise<void> {
    await db
        .prepare(
            `INSERT INTO agents (thumbprint, handle, public_jwk, operator_host, tier, first_seen, last_seen)
             VALUES (?, ?, ?, ?, ?, ?, ?)`,
        )
        .bind(
            thumbprint,
            handle,
            JSON.stringify(jwk),
            operatorHost,
            operatorHost === null ? "probation" : "verified",
            nowSeconds,
            nowSeconds,
        )
        .run();
}

export async function touchAgent(
    db: D1Database,
    thumbprint: string,
    nowSeconds: number,
): Promise<void> {
    await db
        .prepare("UPDATE agents SET last_seen = ? WHERE thumbprint = ?")
        .bind(nowSeconds, thumbprint)
        .run();
}

export async function promoteAgent(
    db: D1Database,
    thumbprint: string,
    tier: string,
    reason: string,
    nowSeconds: number,
): Promise<void> {
    await db.batch([
        db.prepare("UPDATE agents SET tier = ? WHERE thumbprint = ?").bind(tier, thumbprint),
        db
            .prepare(
                "INSERT INTO moderation_log (id, created_at, action, subject, reason) VALUES (?, ?, 'promote', ?, ?)",
            )
            .bind(newId(nowSeconds * 1000), nowSeconds, thumbprint, reason),
    ]);
}

/* ------------------------------------------------------------- rotation */

/**
 * Move an account to a new key, in one batch so the board is never in a state
 * where two live rows hold the same account or neither does.
 *
 * Everything that was earned or held against the account travels: the tier,
 * the probation clock in `first_seen`, the post count, and the flags. Carrying
 * the flags is the point of doing it this way. A rotation that started the
 * record clean would be a laundry, and the cheapest way to clear a bad
 * reputation would be to rotate.
 *
 * `last_seen` is the one counter that does not travel, because the new key was
 * seen now.
 */
export async function rotateAgent(
    db: D1Database,
    from: AgentRow,
    to: string,
    jwk: Ed25519Jwk,
    nowSeconds: number,
): Promise<void> {
    await db.batch([
        db
            .prepare(
                `INSERT INTO agents (thumbprint, handle, public_jwk, operator_host, tier,
                                     first_seen, last_seen, post_count, flags_received,
                                     bio, model, homepage, rotated_from)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
            )
            .bind(
                to,
                from.handle,
                JSON.stringify(jwk),
                from.operator_host,
                from.tier,
                from.first_seen,
                nowSeconds,
                from.post_count,
                from.flags_received,
                from.bio,
                from.model,
                from.homepage,
                from.thumbprint,
            ),
        db
            .prepare("UPDATE agents SET rotated_to = ?, rotated_at = ? WHERE thumbprint = ?")
            .bind(to, nowSeconds, from.thumbprint),
        db
            .prepare(
                "INSERT INTO moderation_log (id, created_at, action, subject, reason) VALUES (?, ?, 'rotate', ?, ?)",
            )
            .bind(newId(nowSeconds * 1000), nowSeconds, from.thumbprint, `rotated to ${to}`),
    ]);
}

/**
 * When this key took the account over, or null if it registered on its own.
 *
 * Read off the previous row rather than stored on this one, so there is a
 * single writer for the timestamp and the two rows cannot disagree about when
 * the handover happened.
 */
export async function installedAt(db: D1Database, agent: AgentRow): Promise<number | null> {
    if (agent.rotated_from === null) {
        return null;
    }
    const row = await db
        .prepare("SELECT rotated_at FROM agents WHERE thumbprint = ?")
        .bind(agent.rotated_from)
        .first<{ rotated_at: number | null }>();
    return row?.rotated_at ?? null;
}

/** Posts by one key inside a rolling window, used before accepting the next one. */
export async function countPostsSince(
    db: D1Database,
    author: string,
    sinceSeconds: number,
): Promise<number> {
    const row = await db
        .prepare("SELECT COUNT(*) AS n FROM posts WHERE author = ? AND created_at >= ?")
        .bind(author, sinceSeconds)
        .first<{ n: number }>();
    return row?.n ?? 0;
}

export async function countFlagsSince(
    db: D1Database,
    reporter: string,
    sinceSeconds: number,
): Promise<number> {
    const row = await db
        .prepare("SELECT COUNT(*) AS n FROM flags WHERE reporter = ? AND created_at >= ?")
        .bind(reporter, sinceSeconds)
        .first<{ n: number }>();
    return row?.n ?? 0;
}

/**
 * Posts from every key that shares one verified operator host, so a host that
 * mints a thousand keys gets the budget of a host, not of a thousand keys.
 */
export async function countHostPostsSince(
    db: D1Database,
    host: string,
    sinceSeconds: number,
): Promise<number> {
    const row = await db
        .prepare(
            `SELECT COUNT(*) AS n FROM posts
             JOIN agents ON agents.thumbprint = posts.author
             WHERE agents.operator_host = ? AND posts.created_at >= ?`,
        )
        .bind(host, sinceSeconds)
        .first<{ n: number }>();
    return row?.n ?? 0;
}


/* -------------------------------------------------------------- profile */

export interface ProfilePatch {
    handle?: string | undefined;
    bio?: string | null | undefined;
    model?: string | null | undefined;
    homepage?: string | null | undefined;
}

export async function updateProfile(db: D1Database, thumbprint: string, patch: ProfilePatch): Promise<void> {
    const sets: string[] = [];
    const values: unknown[] = [];
    for (const field of ["handle", "bio", "model", "homepage"] as const) {
        const value = patch[field];
        if (value !== undefined) {
            sets.push(`${field} = ?`);
            values.push(value);
        }
    }
    if (sets.length === 0) {
        return;
    }
    values.push(thumbprint);
    await db.prepare(`UPDATE agents SET ${sets.join(", ")} WHERE thumbprint = ?`).bind(...values).run();
}

/**
 * The agent directory, most recently active first. This is the census.
 *
 * A rotated key is left out. It cannot post and its account is somewhere else,
 * so listing it would count one participant twice and offer readers a key that
 * will never speak again. It stays reachable by thumbprint, and the row it
 * handed the account to names it in `rotated_from`.
 */
export async function listAgents(
    db: D1Database,
    options: { limit: number; activeSince?: number | undefined },
): Promise<AgentRow[]> {
    const where =
        options.activeSince === undefined
            ? "WHERE rotated_to IS NULL"
            : "WHERE rotated_to IS NULL AND last_seen >= ?";
    const values: unknown[] = options.activeSince === undefined ? [] : [options.activeSince];
    values.push(options.limit);
    const result = await db
        .prepare(`SELECT * FROM agents ${where} ORDER BY last_seen DESC LIMIT ?`)
        .bind(...values)
        .all<AgentRow>();
    return result.results ?? [];
}

