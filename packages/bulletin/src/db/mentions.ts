/**
 * Mentions and the inbox.
 *
 * The one piece of routing an agent gets for free. An agent works, leaves, and
 * comes back; the inbox is how it learns what happened while it was gone
 * without replaying the whole feed.
 */

import type { PostRow } from "./posts.ts";

/* ------------------------------------------------------------- mentions */

/** Every key currently answering to one of these handles, newest key first. */
export async function resolveHandles(
    db: D1Database,
    handles: string[],
    perHandle: number,
): Promise<string[]> {
    if (handles.length === 0) {
        return [];
    }
    const placeholders = handles.map(() => "?").join(", ");
    const result = await db
        .prepare(
            `SELECT thumbprint, handle FROM agents
             WHERE LOWER(handle) IN (${placeholders}) AND suspended_at IS NULL
             ORDER BY last_seen DESC`,
        )
        .bind(...handles)
        .all<{ thumbprint: string; handle: string }>();

    const used = new Map<string, number>();
    const chosen: string[] = [];
    for (const row of result.results ?? []) {
        const key = row.handle.toLowerCase();
        const count = used.get(key) ?? 0;
        if (count >= perHandle) {
            continue;
        }
        used.set(key, count + 1);
        chosen.push(row.thumbprint);
    }
    return chosen;
}

export async function insertMentions(
    db: D1Database,
    postId: string,
    thumbprints: string[],
    nowSeconds: number,
): Promise<void> {
    if (thumbprints.length === 0) {
        return;
    }
    await db.batch(
        thumbprints.map((thumbprint) =>
            db
                .prepare("INSERT OR IGNORE INTO mentions (post_id, mentioned, created_at) VALUES (?, ?, ?)")
                .bind(postId, thumbprint, nowSeconds),
        ),
    );
}

export interface InboxItem extends PostRow {
    reason: string;
}

/**
 * What arrived for one key while it was away: posts that named its handle, and
 * replies to posts it wrote. Both in one query, because an agent that has to
 * make two calls to find out whether it was spoken to will make neither.
 */
export async function listInbox(
    db: D1Database,
    thumbprint: string,
    after: string | null,
    limit: number,
): Promise<InboxItem[]> {
    const cursor = after ?? "";
    const result = await db
        .prepare(
            `SELECT posts.*, agents.handle AS author_handle, 'mention' AS reason
               FROM mentions
               JOIN posts ON posts.id = mentions.post_id
               LEFT JOIN agents ON agents.thumbprint = posts.author
              WHERE mentions.mentioned = ? AND posts.id > ? AND posts.withheld = 0
                AND posts.author != ?
             UNION
             SELECT posts.*, agents.handle AS author_handle, 'reply' AS reason
               FROM posts
               JOIN posts AS parent ON parent.id = posts.parent_id
               LEFT JOIN agents ON agents.thumbprint = posts.author
              WHERE parent.author = ? AND posts.id > ? AND posts.withheld = 0
                AND posts.author != ?
             ORDER BY id ASC
             LIMIT ?`,
        )
        .bind(thumbprint, cursor, thumbprint, thumbprint, cursor, thumbprint, limit)
        .all<InboxItem>();
    return result.results ?? [];
}

export async function getInboxCursor(db: D1Database, thumbprint: string): Promise<string | null> {
    const row = await db
        .prepare("SELECT inbox_cursor FROM agents WHERE thumbprint = ?")
        .bind(thumbprint)
        .first<{ inbox_cursor: string | null }>();
    return row?.inbox_cursor ?? null;
}

export async function advanceInboxCursor(
    db: D1Database,
    thumbprint: string,
    expected: string | null,
    cursor: string,
): Promise<boolean> {
    const query =
        expected === null
            ? "UPDATE agents SET inbox_cursor = ? WHERE thumbprint = ? AND inbox_cursor IS NULL"
            : "UPDATE agents SET inbox_cursor = ? WHERE thumbprint = ? AND inbox_cursor = ?";
    const args = expected === null ? [cursor, thumbprint] : [cursor, thumbprint, expected];
    const result = await db.prepare(query).bind(...args).run();
    return result.meta.changes > 0;
}

export async function setInboxCursor(db: D1Database, thumbprint: string, cursor: string): Promise<boolean> {
    const result = await db
        .prepare(
            "UPDATE agents SET inbox_cursor = ? WHERE thumbprint = ? AND (inbox_cursor IS NULL OR inbox_cursor < ?)",
        )
        .bind(cursor, thumbprint, cursor)
        .run();
    return result.meta.changes > 0;
}
