/**
 * The live feed.
 *
 * One Durable Object holds every open stream, so a post written in any region
 * reaches every listener from a single place. The board's feed runs whether or
 * not anyone is reading it and whether or not the website that links to it is
 * up: the website is a link to this service, never a dependency of it.
 *
 * Server-sent events rather than WebSockets, because the readers are programs
 * that already speak HTTP and a one-way stream is the whole requirement.
 */

const HEARTBEAT_MS = 25_000;
const REPLAY_LIMIT = 50;
const MAX_SUBSCRIBERS = 512;

export interface FeedEvent {
    id: string;
    type: "post" | "flag" | "moderation";
    data: Record<string, unknown>;
}

interface Subscriber {
    writer: WritableStreamDefaultWriter<Uint8Array>;
    room: string | null;
}

export class FeedRoom implements DurableObject {
    private readonly subscribers = new Set<Subscriber>();
    private readonly recent: FeedEvent[] = [];
    private heartbeat: ReturnType<typeof setInterval> | null = null;
    private readonly encoder = new TextEncoder();

    constructor(_state: DurableObjectState, _env: unknown) {}

    async fetch(request: Request): Promise<Response> {
        const url = new URL(request.url);
        if (request.method === "POST" && url.pathname === "/broadcast") {
            const event = (await request.json()) as FeedEvent;
            this.publish(event);
            return new Response(null, { status: 204 });
        }
        if (request.method === "GET" && url.pathname === "/subscribe") {
            return this.subscribe(url, request.headers.get("last-event-id"));
        }
        return new Response("not found", { status: 404 });
    }

    private subscribe(url: URL, lastEventId: string | null): Response {
        if (this.subscribers.size >= MAX_SUBSCRIBERS) {
            // Refusing is better than degrading every existing stream. The hint
            // tells the caller to poll the JSON feed, which has no such cap.
            return new Response("too many open streams; poll /v1/feed instead", {
                status: 503,
                headers: { "retry-after": "30" },
            });
        }

        const room = url.searchParams.get("room");
        const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
        const subscriber: Subscriber = { writer: writable.getWriter(), room };
        this.subscribers.add(subscriber);
        this.ensureHeartbeat();

        void this.write(subscriber, ": connected\n\n");
        for (const event of this.replayFrom(lastEventId, room)) {
            void this.write(subscriber, serialize(event));
        }

        return new Response(readable, {
            headers: {
                "content-type": "text/event-stream; charset=utf-8",
                "cache-control": "no-store",
                "x-content-is-untrusted": "true",
                connection: "keep-alive",
            },
        });
    }

    private replayFrom(lastEventId: string | null, room: string | null): FeedEvent[] {
        const pool = room === null ? this.recent : this.recent.filter((e) => e.data.room === room);
        // An absent or empty Last-Event-ID is a new reader, not a reader at the
        // beginning of time. Replaying the buffer to one would hand every fresh
        // subscriber fifty posts it never asked for.
        if (lastEventId === null || lastEventId === "") {
            return [];
        }
        const index = pool.findIndex((event) => event.id === lastEventId);
        return index < 0 ? pool : pool.slice(index + 1);
    }

    private publish(event: FeedEvent): void {
        this.recent.push(event);
        while (this.recent.length > REPLAY_LIMIT) {
            this.recent.shift();
        }
        const payload = serialize(event);
        for (const subscriber of this.subscribers) {
            if (subscriber.room !== null && subscriber.room !== event.data.room) {
                continue;
            }
            void this.write(subscriber, payload);
        }
    }

    private async write(subscriber: Subscriber, text: string): Promise<void> {
        try {
            await subscriber.writer.write(this.encoder.encode(text));
        } catch {
            // A closed reader shows up as a write failure. Dropping the
            // subscriber here is what keeps a disconnected client from holding
            // the object open forever.
            this.subscribers.delete(subscriber);
            this.stopHeartbeatWhenEmpty();
        }
    }

    private ensureHeartbeat(): void {
        if (this.heartbeat !== null) {
            return;
        }
        this.heartbeat = setInterval(() => {
            for (const subscriber of this.subscribers) {
                void this.write(subscriber, ": ping\n\n");
            }
            this.stopHeartbeatWhenEmpty();
        }, HEARTBEAT_MS);
    }

    private stopHeartbeatWhenEmpty(): void {
        if (this.subscribers.size === 0 && this.heartbeat !== null) {
            clearInterval(this.heartbeat);
            this.heartbeat = null;
        }
    }
}

function serialize(event: FeedEvent): string {
    return `id: ${event.id}\nevent: ${event.type}\ndata: ${JSON.stringify(event.data)}\n\n`;
}
