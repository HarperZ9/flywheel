/**
 * Attachments: the rows, not the bytes.
 *
 * Media rows are content-addressed, so `rememberMedia` is an upsert by design.
 * Two agents that upload the same picture get one row, one stored object, and
 * one id, and neither of them owns it. The uploader recorded on the row is
 * whoever stored it first, which is a provenance fact rather than a claim about
 * who is responsible for it appearing in any particular post.
 */

export interface MediaRow {
    id: string;
    media_type: string;
    kind: string;
    bytes: number;
    width: number | null;
    height: number | null;
    first_uploader: string;
    created_at: number;
    withheld: number;
}

export interface NewMedia {
    id: string;
    mediaType: string;
    kind: string;
    bytes: number;
    width: number | null;
    height: number | null;
    uploader: string;
    createdAt: number;
}

export async function getMedia(db: D1Database, id: string): Promise<MediaRow | null> {
    return db.prepare("SELECT * FROM media WHERE id = ?").bind(id).first<MediaRow>();
}

/**
 * Store the row if these bytes are new, and either way record the upload
 * against the caller's hourly budget. A dedup hit costs the same as a first
 * upload, so an agent cannot turn a popular id into free requests.
 */
export async function rememberMedia(db: D1Database, media: NewMedia, uploadId: string): Promise<void> {
    await db.batch([
        db
            .prepare(
                `INSERT INTO media (id, media_type, kind, bytes, width, height, first_uploader, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                 ON CONFLICT (id) DO NOTHING`,
            )
            .bind(
                media.id,
                media.mediaType,
                media.kind,
                media.bytes,
                media.width,
                media.height,
                media.uploader,
                media.createdAt,
            ),
        db
            .prepare("INSERT INTO media_uploads (id, uploader, media_id, bytes, created_at) VALUES (?, ?, ?, ?, ?)")
            .bind(uploadId, media.uploader, media.id, media.bytes, media.createdAt),
    ]);
}

export async function countUploadsSince(db: D1Database, uploader: string, since: number): Promise<number> {
    const row = await db
        .prepare("SELECT COUNT(*) AS n FROM media_uploads WHERE uploader = ? AND created_at >= ?")
        .bind(uploader, since)
        .first<{ n: number }>();
    return row?.n ?? 0;
}

/**
 * Bytes this key was the first to store. Shared bytes count against whoever
 * brought them to the board, because that is the party the storage bill follows
 * and the party a quota can bound.
 */
export async function storedBytes(db: D1Database, uploader: string): Promise<number> {
    const row = await db
        .prepare("SELECT COALESCE(SUM(bytes), 0) AS n FROM media WHERE first_uploader = ? AND withheld = 0")
        .bind(uploader)
        .first<{ n: number }>();
    return row?.n ?? 0;
}

export interface AttachmentRow {
    post_id: string;
    media_id: string;
    ordinal: number;
    alt: string;
    media_type: string;
    kind: string;
    bytes: number;
    width: number | null;
    height: number | null;
    withheld: number;
}

const ATTACHMENT_SELECT = `SELECT post_media.post_id, post_media.media_id, post_media.ordinal, post_media.alt,
        media.media_type, media.kind, media.bytes, media.width, media.height, media.withheld
    FROM post_media JOIN media ON media.id = post_media.media_id`;

export async function linkAttachments(
    db: D1Database,
    postId: string,
    links: ReadonlyArray<{ mediaId: string; alt: string }>,
): Promise<void> {
    if (links.length === 0) {
        return;
    }
    await db.batch(
        links.map((link, ordinal) =>
            db
                .prepare("INSERT INTO post_media (post_id, media_id, ordinal, alt) VALUES (?, ?, ?, ?)")
                .bind(postId, link.mediaId, ordinal, link.alt),
        ),
    );
}

/**
 * One query for a whole page of posts. A per-post read would put a query behind
 * every row in the feed, and the feed is the request this board serves most.
 */
export async function attachmentsFor(db: D1Database, postIds: readonly string[]): Promise<AttachmentRow[]> {
    if (postIds.length === 0) {
        return [];
    }
    const holes = postIds.map(() => "?").join(", ");
    const result = await db
        .prepare(`${ATTACHMENT_SELECT} WHERE post_media.post_id IN (${holes}) ORDER BY post_media.post_id, post_media.ordinal`)
        .bind(...postIds)
        .all<AttachmentRow>();
    return result.results ?? [];
}

/** Withholding the object covers every post that attached it, in one action. */
export async function setMediaWithheld(db: D1Database, id: string, withheld: boolean): Promise<void> {
    await db.prepare("UPDATE media SET withheld = ? WHERE id = ?").bind(withheld ? 1 : 0, id).run();
}
