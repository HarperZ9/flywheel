import { insertPost } from "../src/db.ts";
import type { AgentRow } from "../src/db.ts";
import type { Env } from "../src/config.ts";
import { NOW, OTHER, RECEIVER } from "./inbox-ack-helpers.ts";
import { OrderingStatement } from "./post-ordering-statement.ts";

export const BASE_MILLIS = NOW * 1000;
export const LOW_ID = `${BASE_MILLIS}-AAAAAAAA`;
export const HIGH_ID = `${BASE_MILLIS}-________`;

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

export class OrderingDb {
    readonly agents = new Map<string, AgentRow>();
    readonly posts: Post[] = [];
    readonly mentions: { post_id: string; mentioned: string }[] = [];
    readonly rooms = new Map([[
        "lobby",
        { slug: "lobby", title: "Lobby", purpose: "", created_at: NOW, created_by: "system", locked: 0, post_count: 0 },
    ]]);
    readonly spent = new Map<string, { result_kind: string | null; result_id: string | null }>();
    afterPostOnlyBatch: (() => Promise<void>) | null = null;
    failNextPostInsert = false;

    prepare(sql: string): D1PreparedStatement {
        return new OrderingStatement(this, sql) as unknown as D1PreparedStatement;
    }

    async batch(statements: D1PreparedStatement[]): Promise<D1Result[]> {
        const snapshot = this.snapshot();
        try {
            const wrapped = statements as unknown as OrderingStatement[];
            const results: D1Result[] = [];
            for (const statement of wrapped) results.push(await statement.run() as D1Result);
            if (wrapped.some((statement) => statement.isPostInsert()) && !wrapped.some((statement) => statement.isMentionInsert())) {
                const callback = this.afterPostOnlyBatch;
                this.afterPostOnlyBatch = null;
                await callback?.();
            }
            return results;
        } catch (error) {
            this.restore(snapshot);
            throw error;
        }
    }

    addAgent(row: AgentRow): void {
        this.agents.set(row.thumbprint, { ...row });
    }

    spendNonce(nonce: string): void {
        this.spent.set(nonce, { result_kind: null, result_id: null });
    }

    recordNonce(nonce: string, kind: string, id: string): void {
        this.spent.set(nonce, { result_kind: kind, result_id: id });
    }

    cursor(account: string): string | null {
        return this.agents.get(account)?.inbox_cursor ?? null;
    }

    addMention(postId: string, mentioned: string): void {
        if (!this.mentions.some((entry) => entry.post_id === postId && entry.mentioned === mentioned)) {
            this.mentions.push({ post_id: postId, mentioned });
        }
    }

    addInboxPost(id: string, mentioned: string): void {
        this.insertPostRow(id, "sender-key", `hello ${mentioned}`, "sig");
        this.addMention(id, mentioned);
    }

    insertPostRow(id: string, author: string, body: string, signature: string): void {
        if (this.failNextPostInsert) {
            this.failNextPostInsert = false;
            throw new Error("post insert failed");
        }
        if (this.posts.some((post) => post.id === id)) throw new Error("post insert failed");
        this.posts.push({
            id,
            room: "lobby",
            author,
            parent_id: null,
            body,
            created_at: NOW,
            content_hash: `hash-${id}`,
            signature,
            author_tier: "verified",
            flags_received: 0,
            withheld: 0,
            author_handle: this.agents.get(author)?.handle ?? null,
        });
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

    allocate(candidateMillis: number, suffix: string, nonce: string): number {
        const spent = this.spent.get(nonce);
        if (spent === undefined || spent.result_kind !== null || spent.result_id !== null) return 0;
        let head: string | undefined;
        for (const post of this.posts) {
            if (head === undefined || post.id > head) head = post.id;
        }
        const maxPrefix = head === undefined ? 0 : Number(head.slice(0, 13));
        spent.result_kind = "post_pending";
        spent.result_id = `${String(Math.max(candidateMillis, maxPrefix + 1)).padStart(13, "0")}-${suffix}`;
        return 1;
    }

    finalizePost(nonce: string): number {
        const spent = this.spent.get(nonce);
        if (spent?.result_kind !== "post_pending" || typeof spent.result_id !== "string") return 0;
        if (!this.posts.some((post) => post.id === spent.result_id)) return 0;
        spent.result_kind = "post";
        return 1;
    }

    pendingId(nonce: string): string | null {
        const spent = this.spent.get(nonce);
        return spent?.result_kind === "post_pending" && typeof spent.result_id === "string" ? spent.result_id : null;
    }

    resultId(nonce: string): string | null {
        const spent = this.spent.get(nonce);
        return spent?.result_kind === "post" && typeof spent.result_id === "string" ? spent.result_id : null;
    }

    snapshot(): Snapshot {
        return {
            agents: new Map(Array.from(this.agents, ([key, value]) => [key, { ...value }])),
            posts: this.posts.map((post) => ({ ...post })),
            mentions: this.mentions.map((mention) => ({ ...mention })),
            rooms: new Map(Array.from(this.rooms, ([key, value]) => [key, { ...value }])),
            spent: new Map(Array.from(this.spent, ([key, value]) => [key, { ...value }])),
        };
    }

    restore(snapshot: Snapshot): void {
        this.agents.clear();
        for (const [key, value] of snapshot.agents) this.agents.set(key, value);
        this.posts.length = 0;
        this.posts.push(...snapshot.posts.map((post) => ({ ...post })));
        this.mentions.length = 0;
        this.mentions.push(...snapshot.mentions.map((mention) => ({ ...mention })));
        this.rooms.clear();
        for (const [key, value] of snapshot.rooms) this.rooms.set(key, value);
        this.spent.clear();
        for (const [key, value] of snapshot.spent) this.spent.set(key, value);
    }
}

interface Snapshot {
    agents: Map<string, AgentRow>;
    posts: Post[];
    mentions: { post_id: string; mentioned: string }[];
    rooms: Map<string, { slug: string; title: string; purpose: string; created_at: number; created_by: string; locked: number; post_count: number }>;
    spent: Map<string, { result_kind: string | null; result_id: string | null }>;
}

export async function writeMention(db: OrderingDb, candidateId: string, nonceKey: string): Promise<string> {
    const id = await insertPost(db as unknown as D1Database, {
        candidateId,
        nonceKey,
        room: "lobby",
        author: OTHER,
        parentId: null,
        body: `hello ${RECEIVER}`,
        createdAt: NOW,
        contentHash: `hash-${nonceKey}`,
        signature: `sig-${nonceKey}`,
        authorTier: "verified",
        attachments: [],
        mentions: [RECEIVER],
    });
    return (id as string | undefined) ?? candidateId;
}

export async function withFixedRandomBytes<T>(byte: number, fn: () => Promise<T>): Promise<T> {
    const testCrypto = crypto as unknown as { getRandomValues: <TArray extends ArrayBufferView | null>(array: TArray) => TArray };
    const original = testCrypto.getRandomValues.bind(testCrypto);
    Object.defineProperty(testCrypto, "getRandomValues", {
        configurable: true,
        value: <TArray extends ArrayBufferView | null>(array: TArray): TArray => {
            if (array instanceof Uint8Array) array.fill(byte);
            return array;
        },
    });
    const originalNow = Date.now;
    Date.now = () => BASE_MILLIS;
    try {
        return await fn();
    } finally {
        Object.defineProperty(testCrypto, "getRandomValues", { configurable: true, value: original });
        Date.now = originalNow;
    }
}

export function envWith(db: OrderingDb): Env {
    return { DB: db as unknown as D1Database, KEYS: {} as KVNamespace, FEED: {} as DurableObjectNamespace, BULLETIN_POW_BITS: 20, BULLETIN_SIGNATURE_MAX_AGE: 300, BULLETIN_EMBED_ORIGIN: "https://harperz9.github.io" };
}
