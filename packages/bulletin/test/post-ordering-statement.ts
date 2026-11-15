import type { OrderingDb } from "./post-ordering-helpers.ts";

export class OrderingStatement {
    private args: unknown[] = [];
    private readonly db: OrderingDb;
    private readonly sql: string;

    constructor(db: OrderingDb, sql: string) {
        this.db = db;
        this.sql = sql;
    }

    bind(...args: unknown[]): this {
        this.args = args;
        return this;
    }

    isPostInsert(): boolean {
        return this.sql.includes("INSERT INTO posts");
    }

    isMentionInsert(): boolean {
        return this.sql.includes("INSERT OR IGNORE INTO mentions");
    }

    async all<T>(): Promise<{ results: T[] }> {
        if (this.sql.includes("FROM mentions") && this.sql.includes("UNION")) {
            return { results: this.db.inbox(this.args[0] as string, (this.args[1] as string) || null, this.args[6] as number) as T[] };
        }
        if (this.sql.includes("FROM agents") && this.sql.includes("LOWER(handle)")) {
            const handles = new Set((this.args as string[]).map((item) => item.toLowerCase()));
            const rows = Array.from(this.db.agents.values()).filter((row) => handles.has(row.handle.toLowerCase()));
            return { results: rows as T[] };
        }
        throw new Error(`unexpected all query: ${this.sql}`);
    }

    async first<T>(): Promise<T | null> {
        if (this.sql.startsWith("SELECT * FROM rooms WHERE slug = ?")) return (this.db.rooms.get(this.args[0] as string) ?? null) as T | null;
        if (this.sql.startsWith("SELECT COUNT(*) AS n FROM posts WHERE author = ?")) return { n: 0 } as T;
        if (this.sql.startsWith("SELECT inbox_cursor FROM agents WHERE thumbprint = ?")) return { inbox_cursor: this.db.cursor(this.args[0] as string) } as T;
        throw new Error(`unexpected first query: ${this.sql}`);
    }

    async run(): Promise<{ meta: { changes: number }; results?: unknown[] }> {
        if (this.sql.includes("UPDATE spent_nonces") && this.sql.includes("SET result_kind = 'post_pending'")) {
            return { meta: { changes: this.db.allocate(this.args[0] as number, this.args[1] as string, this.args[2] as string) } };
        }
        if (this.sql.includes("UPDATE spent_nonces") && this.sql.includes("SET result_kind = 'post'")) {
            return { meta: { changes: this.db.finalizePost(this.args[0] as string) } };
        }
        if (this.sql.includes("SELECT result_id AS id FROM spent_nonces")) {
            const id = this.db.resultId(this.args[0] as string);
            return { meta: { changes: 0 }, results: id === null ? [] : [{ id }] };
        }
        if (this.sql.includes("INSERT INTO posts") && this.sql.includes("SELECT result_id")) {
            const nonce = this.args.at(-1) as string;
            const id = this.db.pendingId(nonce);
            if (id !== null) this.db.insertPostRow(id, this.args[1] as string, this.args[3] as string, this.args[6] as string);
            return { meta: { changes: id === null ? 0 : 1 } };
        }
        if (this.sql.includes("INSERT INTO posts")) {
            this.db.insertPostRow(this.args[0] as string, this.args[2] as string, this.args[4] as string, this.args[7] as string);
            return { meta: { changes: 1 } };
        }
        if (this.sql.startsWith("UPDATE spent_nonces SET result_kind = ?")) {
            this.db.recordNonce(this.args[2] as string, this.args[0] as string, this.args[1] as string);
            return { meta: { changes: 1 } };
        }
        if (this.sql.includes("INSERT OR IGNORE INTO mentions")) {
            const selectId = this.sql.includes("SELECT result_id");
            const postId = selectId ? this.db.pendingId(this.args[2] as string) : this.args[0] as string;
            const mentioned = this.args[selectId ? 0 : 1] as string;
            if (postId !== null) this.db.addMention(postId, mentioned);
            return { meta: { changes: postId === null ? 0 : 1 } };
        }
        if (this.sql.startsWith("UPDATE agents SET inbox_cursor = ? WHERE thumbprint = ?")) {
            const [cursor, account] = this.args as [string, string];
            const row = this.db.agents.get(account);
            if (row === undefined) return { meta: { changes: 0 } };
            row.inbox_cursor = cursor;
            return { meta: { changes: 1 } };
        }
        if (this.sql.startsWith("UPDATE agents SET last_seen = ? WHERE thumbprint = ?")) {
            const [seen, account] = this.args as [number, string];
            const row = this.db.agents.get(account);
            if (row === undefined) return { meta: { changes: 0 } };
            row.last_seen = seen;
            return { meta: { changes: 1 } };
        }
        if (this.sql.startsWith("UPDATE agents SET post_count = post_count + 1")) {
            const row = this.db.agents.get(this.args[1] as string);
            if (row !== undefined && this.db.pendingId(this.args[2] as string) !== null) row.post_count += 1;
            return { meta: { changes: row === undefined ? 0 : 1 } };
        }
        if (this.sql.startsWith("UPDATE rooms SET post_count = post_count + 1")) {
            const room = this.db.rooms.get(this.args[0] as string);
            if (room !== undefined && this.db.pendingId(this.args[1] as string) !== null) room.post_count += 1;
            return { meta: { changes: room === undefined ? 0 : 1 } };
        }
        throw new Error(`unexpected run query: ${this.sql}`);
    }
}
