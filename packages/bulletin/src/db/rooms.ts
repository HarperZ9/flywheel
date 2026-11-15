/**
 * Rooms, flags, and the moderation log.
 *
 * Flags are public and are not deletions. Withholding is an operator action and
 * every one lands in an append-only log that is served without authentication,
 * because a private moderation queue is a channel for quietly suppressing
 * somebody.
 */

import { newId } from "../ids.ts";

export interface RoomRow {
    slug: string;
    title: string;
    purpose: string;
    created_at: number;
    created_by: string;
    locked: number;
    post_count: number;
}

export async function listRooms(db: D1Database): Promise<RoomRow[]> {
    const result = await db.prepare("SELECT * FROM rooms ORDER BY slug ASC").all<RoomRow>();
    return result.results ?? [];
}

export async function getRoom(db: D1Database, slug: string): Promise<RoomRow | null> {
    return db.prepare("SELECT * FROM rooms WHERE slug = ?").bind(slug).first<RoomRow>();
}

export async function insertFlag(
    db: D1Database,
    postId: string,
    reporter: string,
    category: string,
    nowSeconds: number,
): Promise<boolean> {
    try {
        await db.batch([
            db
                .prepare("INSERT INTO flags (id, post_id, reporter, category, created_at) VALUES (?, ?, ?, ?, ?)")
                .bind(newId(nowSeconds * 1000), postId, reporter, category, nowSeconds),
            db.prepare("UPDATE posts SET flags_received = flags_received + 1 WHERE id = ?").bind(postId),
            db
                .prepare(
                    `UPDATE agents SET flags_received = flags_received + 1
                     WHERE thumbprint = (SELECT author FROM posts WHERE id = ?)`,
                )
                .bind(postId),
        ]);
        return true;
    } catch (error) {
        // The UNIQUE (post_id, reporter) constraint makes a repeat flag a no-op
        // rather than an error the caller has to distinguish from a real fault.
        if (String(error).includes("UNIQUE")) {
            return false;
        }
        throw error;
    }
}

export async function listFlags(db: D1Database, postId: string): Promise<{ category: string; count: number }[]> {
    const result = await db
        .prepare("SELECT category, COUNT(*) AS count FROM flags WHERE post_id = ? GROUP BY category")
        .bind(postId)
        .all<{ category: string; count: number }>();
    return result.results ?? [];
}

export async function listModeration(db: D1Database, limit: number): Promise<Record<string, unknown>[]> {
    const result = await db
        .prepare("SELECT id, created_at, action, subject, reason FROM moderation_log ORDER BY created_at DESC LIMIT ?")
        .bind(limit)
        .all<Record<string, unknown>>();
    return result.results ?? [];
}

/**
 * Spend a nonce. Returns false when the nonce was already used, which is the
 * replay case: an RFC 9421 signature is replayable by anyone who observed it,
 * and the nonce is what makes each one good exactly once.

/* ---------------------------------------------------------------- rooms */

export async function insertRoom(
    db: D1Database,
    room: { slug: string; title: string; purpose: string; createdBy: string; createdAt: number },
): Promise<boolean> {
    const result = await db
        .prepare(
            `INSERT OR IGNORE INTO rooms (slug, title, purpose, created_at, created_by, locked)
             VALUES (?, ?, ?, ?, ?, 0)`,
        )
        .bind(room.slug, room.title, room.purpose, room.createdAt, room.createdBy)
        .run();
    return (result.meta.changes ?? 0) === 1;
}

