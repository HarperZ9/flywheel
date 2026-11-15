import type { Env } from "../src/worker.ts";

export const NOW = 1_800_000_000;
export const RECEIVER = "receiver-key";
export const OTHER = "other-key";

export interface Agent {
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
    bio: string | null;
    model: string | null;
    homepage: string | null;
    inbox_cursor: string | null;
    rotated_to: string | null;
    rotated_at: number | null;
    rotated_from: string | null;
}

interface Post {
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
    author_handle: string | null;
}

export class InboxDb {
    readonly agents = new Map<string, Agent>();
    readonly posts: Post[] = [];
    readonly mentions: { post_id: string; mentioned: string }[] = [];
    readonly spent = new Set<string>();
    beforeCursorUpdate: (() => void) | null = null;

    prepare(sql: string): D1PreparedStatement {
        return new Statement(this, sql) as unknown as D1PreparedStatement;
    }

    async batch(statements: D1PreparedStatement[]): Promise<D1Result[]> {
        const results = [];
        for (const statement of statements as unknown as Statement[]) {
            results.push(await statement.run());
        }
        return results as unknown as D1Result[];
    }

    cursor(account: string): string | null {
        return this.agents.get(account)?.inbox_cursor ?? null;
    }

    addAgent(agent: Agent): void {
        this.agents.set(agent.thumbprint, { ...agent });
    }

    addInboxPost(id: string, mentioned = RECEIVER): void {
        this.posts.push({
            id,
            room: "agent-tooling",
            author: "sender-key",
            parent_id: null,
            body: `hello ${mentioned}`,
            created_at: NOW,
            content_hash: `hash-${id}`,
            signature: "sig",
            author_tier: "verified",
            flags_received: 0,
            withheld: 0,
            author_handle: "sender",
        });
        this.mentions.push({ post_id: id, mentioned });
    }

    inbox(account: string, after: string | null, limit: number): Array<Post & { reason: string }> {
        const cursor = after ?? "";
        return this.posts
            .filter((post) => post.id > cursor && post.withheld === 0 && post.author !== account)
            .filter((post) => this.mentions.some((mention) => mention.post_id === post.id && mention.mentioned === account))
            .sort((a, b) => a.id.localeCompare(b.id))
            .slice(0, limit)
            .map((post) => ({ ...post, reason: "mention" }));
    }

    runBeforeCursorUpdate(): void {
        const callback = this.beforeCursorUpdate;
        this.beforeCursorUpdate = null;
        callback?.();
    }
}

class Statement {
    private args: unknown[] = [];
    private readonly db: InboxDb;
    private readonly sql: string;

    constructor(db: InboxDb, sql: string) {
        this.db = db;
        this.sql = sql;
    }

    bind(...args: unknown[]): this {
        this.args = args;
        return this;
    }

    async all<T>(): Promise<{ results: T[] }> {
        if (this.sql.includes("FROM mentions") && this.sql.includes("UNION")) {
            return { results: this.db.inbox(this.args[0] as string, (this.args[1] as string) || null, this.args[6] as number) as T[] };
        }
        if (this.sql.includes("FROM post_media")) {
            return { results: [] };
        }
        throw new Error(`unexpected all query: ${this.sql}`);
    }

    async first<T>(): Promise<T | null> {
        if (this.sql.startsWith("SELECT * FROM agents WHERE thumbprint = ?")) {
            return (this.db.agents.get(this.args[0] as string) ?? null) as T | null;
        }
        if (this.sql.startsWith("SELECT inbox_cursor FROM agents WHERE thumbprint = ?")) {
            const agent = this.db.agents.get(this.args[0] as string);
            return (agent === undefined ? null : { inbox_cursor: agent.inbox_cursor }) as T | null;
        }
        if (this.sql.startsWith("SELECT result_kind, result_id FROM spent_nonces WHERE nonce = ?")) {
            return null;
        }
        throw new Error(`unexpected first query: ${this.sql}`);
    }

    async run(): Promise<{ meta: { changes: number } }> {
        if (this.sql.startsWith("UPDATE agents SET inbox_cursor = ? WHERE thumbprint = ? AND inbox_cursor IS NULL")) {
            const [cursor, account] = this.args as [string, string];
            this.db.runBeforeCursorUpdate();
            const agent = this.db.agents.get(account);
            if (agent !== undefined && agent.inbox_cursor === null) {
                agent.inbox_cursor = cursor;
                return { meta: { changes: 1 } };
            }
            return { meta: { changes: 0 } };
        }
        if (this.sql.startsWith("UPDATE agents SET inbox_cursor = ? WHERE thumbprint = ? AND inbox_cursor = ?")) {
            const [cursor, account, expected] = this.args as [string, string, string];
            this.db.runBeforeCursorUpdate();
            const agent = this.db.agents.get(account);
            if (agent !== undefined && agent.inbox_cursor === expected) {
                agent.inbox_cursor = cursor;
                return { meta: { changes: 1 } };
            }
            return { meta: { changes: 0 } };
        }
        if (this.sql.startsWith("UPDATE agents SET inbox_cursor = ?")) {
            const [cursor, account, guard] = this.args as [string, string, string];
            this.db.runBeforeCursorUpdate();
            const agent = this.db.agents.get(account);
            if (agent !== undefined && (agent.inbox_cursor === null || agent.inbox_cursor < guard)) {
                agent.inbox_cursor = cursor;
                return { meta: { changes: 1 } };
            }
            return { meta: { changes: 0 } };
        }
        if (this.sql.startsWith("UPDATE agents SET last_seen = ?")) {
            const [seen, account] = this.args as [number, string];
            const agent = this.db.agents.get(account);
            if (agent !== undefined) {
                agent.last_seen = seen;
                return { meta: { changes: 1 } };
            }
            return { meta: { changes: 0 } };
        }
        if (this.sql.startsWith("INSERT OR IGNORE INTO spent_nonces")) {
            const nonce = this.args[0] as string;
            if (this.db.spent.has(nonce)) {
                return { meta: { changes: 0 } };
            }
            this.db.spent.add(nonce);
            return { meta: { changes: 1 } };
        }
        throw new Error(`unexpected run query: ${this.sql}`);
    }
}

export function envWith(db: InboxDb): Env {
    return {
        DB: db as unknown as D1Database,
        KEYS: {} as KVNamespace,
        FEED: {} as DurableObjectNamespace,
        BULLETIN_POW_BITS: 20,
        BULLETIN_SIGNATURE_MAX_AGE: 300,
        BULLETIN_EMBED_ORIGIN: "https://harperz9.github.io",
    };
}

export function agent(thumbprint = RECEIVER, publicJwk = "{}"): Agent {
    return {
        thumbprint,
        handle: thumbprint,
        public_jwk: publicJwk,
        operator_host: null,
        tier: "verified",
        first_seen: NOW,
        last_seen: NOW,
        post_count: 0,
        flags_received: 0,
        suspended_at: null,
        bio: null,
        model: null,
        homepage: null,
        inbox_cursor: null,
        rotated_to: null,
        rotated_at: null,
        rotated_from: null,
    };
}
