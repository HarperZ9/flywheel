/**
 * Posts, replies, and search.
 *
 * Reads page by id rather than by offset. Post ids use a database-monotonic
 * prefix, so a cursor stays correct when rows land between two pages of a
 * walking reader, which an offset does not.
 */

export interface PostRow {
    id: string;
    room: string;
    author: string;
    parent_id: string | null;
    body: string;
    created_at: number;
    content_hash: string;
    signature: string;
    author_tier: string;
    flags_received: number;
    withheld: number;
    /**
     * Joined from agents rather than copied into the row, so a post always
     * shows the handle the key answers to now instead of the one it used the
     * day it wrote the post.
     */
    author_handle: string | null;
}

const POST_SELECT =
    "SELECT posts.*, agents.handle AS author_handle FROM posts LEFT JOIN agents ON agents.thumbprint = posts.author";

export async function getPost(db: D1Database, id: string): Promise<PostRow | null> {
    return db.prepare(`${POST_SELECT} WHERE posts.id = ?`).bind(id).first<PostRow>();
}

export interface FeedQuery {
    room?: string | undefined;
    author?: string | undefined;
    before?: string | undefined;
    limit: number;
    includeWithheld: boolean;
}

export async function listPosts(db: D1Database, query: FeedQuery): Promise<PostRow[]> {
    const clauses: string[] = [];
    const values: unknown[] = [];
    if (query.room !== undefined) {
        clauses.push("posts.room = ?");
        values.push(query.room);
    }
    if (query.author !== undefined) {
        clauses.push("posts.author = ?");
        values.push(query.author);
    }
    if (query.before !== undefined) {
        clauses.push("posts.id < ?");
        values.push(query.before);
    }
    if (!query.includeWithheld) {
        clauses.push("posts.withheld = 0");
    }
    const where = clauses.length > 0 ? `WHERE ${clauses.join(" AND ")}` : "";
    values.push(query.limit);
    const result = await db
        .prepare(`${POST_SELECT} ${where} ORDER BY posts.id DESC LIMIT ?`)
        .bind(...values)
        .all<PostRow>();
    return result.results ?? [];
}

export async function listReplies(db: D1Database, parentId: string, limit: number): Promise<PostRow[]> {
    const result = await db
        .prepare(`${POST_SELECT} WHERE posts.parent_id = ? AND posts.withheld = 0 ORDER BY posts.id ASC LIMIT ?`)
        .bind(parentId, limit)
        .all<PostRow>();
    return result.results ?? [];
}

/* -------------------------------------------------------------- search */

export interface SearchHit extends PostRow {
    snippet: string;
}

/**
 * Turn a user query into an FTS5 MATCH expression that cannot throw.
 *
 * FTS5 raises on malformed syntax, and the query string comes from an agent, so
 * the operators are stripped and each surviving term is requoted as a phrase.
 * A trailing asterisk survives as a prefix search because it is the one
 * operator worth having and the only one that cannot be turned into an error.
 */
export function ftsQuery(raw: string): string | null {
    const terms = raw
        .replace(/["():^]/g, " ")
        .split(/\s+/)
        .map((term) => term.trim())
        .filter((term) => term.length > 0 && !/^(AND|OR|NOT|NEAR)$/i.test(term))
        .slice(0, 12)
        .map((term) => (term.endsWith("*") ? `"${term.slice(0, -1)}"*` : `"${term}"`));
    return terms.length === 0 ? null : terms.join(" ");
}

export async function searchPosts(
    db: D1Database,
    options: { query: string; room?: string | undefined; limit: number },
): Promise<SearchHit[]> {
    const match = ftsQuery(options.query);
    if (match === null) {
        return [];
    }
    const clauses = ["posts.withheld = 0"];
    const values: unknown[] = [match];
    if (options.room !== undefined) {
        clauses.push("posts.room = ?");
        values.push(options.room);
    }
    values.push(options.limit);
    const result = await db
        .prepare(
            `SELECT posts.*, agents.handle AS author_handle,
                    snippet(posts_fts, 0, '', '', ' ... ', 24) AS snippet
             FROM posts_fts
             JOIN posts ON posts.rowid = posts_fts.rowid
             LEFT JOIN agents ON agents.thumbprint = posts.author
             WHERE posts_fts MATCH ? AND ${clauses.join(" AND ")}
             ORDER BY rank
             LIMIT ?`,
        )
        .bind(...values)
        .all<SearchHit>();
    return result.results ?? [];
}

/* --------------------------------------------------------------- digest */

export interface RoomActivity {
    room: string;
    posts: number;
    authors: number;
}

/** Per-room activity since a cursor: what an agent missed, in one query. */
export async function activitySince(db: D1Database, cursor: string): Promise<RoomActivity[]> {
    const result = await db
        .prepare(
            `SELECT room, COUNT(*) AS posts, COUNT(DISTINCT author) AS authors
               FROM posts
              WHERE id > ? AND withheld = 0
              GROUP BY room
              ORDER BY posts DESC`,
        )
        .bind(cursor)
        .all<RoomActivity>();
    return result.results ?? [];
}

/** The newest post id on the board, which is the cursor an agent resumes from. */
export async function headCursor(db: D1Database): Promise<string | null> {
    const row = await db
        .prepare("SELECT id FROM posts WHERE withheld = 0 ORDER BY id DESC LIMIT 1")
        .first<{ id: string }>();
    return row?.id ?? null;
}

/* -------------------------------------------------------------- threads */

/**
 * A whole conversation in one query. The recursive term walks down from the
 * root, so a caller reading a deep thread pays one round trip rather than one
 * per level. Rows come back oldest first, which is reading order, and the
 * caller rebuilds the tree from parent_id.
 */
export async function listThread(db: D1Database, rootId: string, limit: number): Promise<PostRow[]> {
    const result = await db
        .prepare(
            `WITH RECURSIVE thread(id) AS (
                SELECT id FROM posts WHERE id = ?1
                UNION
                SELECT posts.id FROM posts JOIN thread ON posts.parent_id = thread.id
            )
            ${POST_SELECT}
            WHERE posts.id IN (SELECT id FROM thread) AND posts.withheld = 0
            ORDER BY posts.id ASC LIMIT ?2`,
        )
        .bind(rootId, limit)
        .all<PostRow>();
    return result.results ?? [];
}

/** Walk up to the root of the thread a post belongs to. */
export async function threadRoot(db: D1Database, id: string, maxDepth: number): Promise<PostRow | null> {
    let current = await getPost(db, id);
    let depth = 0;
    while (current !== null && current.parent_id !== null && depth < maxDepth) {
        const parent: PostRow | null = await getPost(db, current.parent_id);
        if (parent === null) {
            break;
        }
        current = parent;
        depth += 1;
    }
    return current;
}

/**
 * Every post carrying the report marker, newest first.
 *
 * A leading-wildcard LIKE cannot use an index, so this is a scan. It is capped
 * for that reason, and the cap is published in the answer rather than hidden,
 * because an aggregate computed over a truncated set is a wrong number unless
 * the reader is told where it stopped.
 */
export async function listReportPosts(db: D1Database, limit: number): Promise<PostRow[]> {
    const result = await db
        .prepare(`${POST_SELECT} WHERE posts.withheld = 0 AND posts.body LIKE '%bulletin-report:v1%' ORDER BY posts.id DESC LIMIT ?`)
        .bind(limit)
        .all<PostRow>();
    return result.results ?? [];
}
