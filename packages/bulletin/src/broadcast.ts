/**
 * The one call that reaches the live feed.
 *
 * It is a separate module so a route never imports the Durable Object class,
 * which would pull the whole stream implementation into every request path.
 */

import type { Env } from "./config.ts";
import type { FeedEvent } from "./feed.ts";

export async function broadcast(env: Env, event: FeedEvent): Promise<void> {
    const stub = env.FEED.get(env.FEED.idFromName("global"));
    await stub.fetch("https://feed.invalid/broadcast", {
        method: "POST",
        body: JSON.stringify(event),
        headers: { "content-type": "application/json" },
    });
}
