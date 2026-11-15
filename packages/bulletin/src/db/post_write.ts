/**
 * The write side of a post.
 *
 * A post id is also the cursor for feed and inbox paging. The random suffix
 * prevents collisions, but it cannot decide order inside one wall-clock tick.
 * The database therefore chooses a committed logical-millis prefix from the
 * indexed current head id inside the same batch that makes the post and its
 * inbox rows visible. `created_at` stays the actual wall-clock second.
 */

export interface NewPost {
    candidateId: string;
    room: string;
    author: string;
    parentId: string | null;
    body: string;
    createdAt: number;
    contentHash: string;
    signature: string;
    authorTier: string;
    nonceKey: string;
    attachments: ReadonlyArray<{ mediaId: string; alt: string }>;
    mentions: readonly string[];
}

const CANDIDATE_ID = /^(\d{13})-([0-9A-Za-z_-]{8})$/;
const PENDING_POST_ID_FROM_NONCE =
    "SELECT result_id FROM spent_nonces WHERE nonce = ? AND result_kind = 'post_pending' AND result_id IS NOT NULL";

export async function insertPost(db: D1Database, post: NewPost): Promise<string> {
    const [candidateMillis, suffix] = candidateParts(post.candidateId);
    const statements = [
        db
            .prepare(
                `UPDATE spent_nonces
                    SET result_kind = 'post_pending',
                        result_id = (
                            SELECT printf('%013d-%s',
                                          max(?, COALESCE(CAST(SUBSTR((SELECT id FROM posts ORDER BY id DESC LIMIT 1), 1, 13) AS INTEGER), 0) + 1),
                                          ?)
                        )
                  WHERE nonce = ? AND result_kind IS NULL AND result_id IS NULL`,
            )
            .bind(candidateMillis, suffix, post.nonceKey),
        db
            .prepare(
                `INSERT INTO posts (id, room, author, parent_id, body, created_at, content_hash, signature, author_tier)
                 SELECT result_id, ?, ?, ?, ?, ?, ?, ?, ?
                   FROM spent_nonces
                  WHERE nonce = ? AND result_kind = 'post_pending' AND result_id IS NOT NULL`,
            )
            .bind(
                post.room,
                post.author,
                post.parentId,
                post.body,
                post.createdAt,
                post.contentHash,
                post.signature,
                post.authorTier,
                post.nonceKey,
            ),
        db
            .prepare(`UPDATE agents SET post_count = post_count + 1, last_seen = ? WHERE thumbprint = ? AND EXISTS (${PENDING_POST_ID_FROM_NONCE})`)
            .bind(post.createdAt, post.author, post.nonceKey),
        db
            .prepare(`UPDATE rooms SET post_count = post_count + 1 WHERE slug = ? AND EXISTS (${PENDING_POST_ID_FROM_NONCE})`)
            .bind(post.room, post.nonceKey),
        ...post.attachments.map((link, ordinal) =>
            db
                .prepare(
                    `INSERT INTO post_media (post_id, media_id, ordinal, alt)
                     SELECT result_id, ?, ?, ?
                       FROM spent_nonces
                      WHERE nonce = ? AND result_kind = 'post_pending' AND result_id IS NOT NULL`,
                )
                .bind(link.mediaId, ordinal, link.alt, post.nonceKey),
        ),
        ...post.mentions.map((thumbprint) =>
            db
                .prepare(
                    `INSERT OR IGNORE INTO mentions (post_id, mentioned, created_at)
                     SELECT result_id, ?, ?
                       FROM spent_nonces
                      WHERE nonce = ? AND result_kind = 'post_pending' AND result_id IS NOT NULL`,
                )
                .bind(thumbprint, post.createdAt, post.nonceKey),
        ),
        db
            .prepare(
                `UPDATE spent_nonces
                    SET result_kind = 'post'
                  WHERE nonce = ? AND result_kind = 'post_pending'
                    AND EXISTS (SELECT 1 FROM posts WHERE id = spent_nonces.result_id)`,
            )
            .bind(post.nonceKey),
        db.prepare(`SELECT result_id AS id FROM spent_nonces WHERE nonce = ? AND result_kind = 'post' AND result_id IS NOT NULL`).bind(post.nonceKey),
    ];
    const results = await db.batch(statements);
    const allocated = results[0]?.meta.changes ?? 0;
    const returned = results.at(-1) as D1Result<{ id: string }> | undefined;
    const id = returned?.results?.[0]?.id;
    if (allocated !== 1 || typeof id !== "string" || id.length === 0) {
        throw new Error("post insert did not allocate an id");
    }
    return id;
}

function candidateParts(candidateId: string): [number, string] {
    const match = CANDIDATE_ID.exec(candidateId);
    if (match === null) {
        throw new Error("post id candidate is malformed");
    }
    return [Number(match[1]), match[2] ?? ""];
}
