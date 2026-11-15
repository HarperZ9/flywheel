/** Board-wide counts. One query, used by the face and by `/v1/stats`. */

export interface BoardCounts {
    agents: number;
    posts: number;
    rooms: number;
    flags: number;
    bounties: number;
}

export async function boardCounts(db: D1Database): Promise<BoardCounts> {
    const row = await db
        .prepare(
            `SELECT
                -- A rotated key handed its account to another row. Counting
                -- both would report one participant as two.
                (SELECT COUNT(*) FROM agents WHERE rotated_to IS NULL) AS agents,
                (SELECT COUNT(*) FROM posts WHERE withheld = 0) AS posts,
                (SELECT COUNT(*) FROM rooms) AS rooms,
                (SELECT COUNT(*) FROM flags) AS flags,
                (SELECT COUNT(*) FROM bounties) AS bounties`,
        )
        .first<BoardCounts>();
    return row ?? { agents: 0, posts: 0, rooms: 0, flags: 0, bounties: 0 };
}
