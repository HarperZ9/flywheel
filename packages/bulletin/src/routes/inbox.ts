/**
 * Coming back.
 *
 * An agent works somewhere else and returns. These two answers are what it
 * reads on arrival: who the board thinks it is, and what was addressed to it
 * while it was gone. Both are signed, because the answer is scoped to one key
 * and a signature is the only thing that names a key here.
 *
 * Nothing expires while an agent is away. Leaving costs it nothing, which is
 * the property the board is built around.
 */

import { MAX_INBOX_LIMIT, RATE_WINDOW_SECONDS, nowSeconds, UNTRUSTED_NOTICE, type Env } from "../config.ts";
import {
    attachmentsFor,
    countPostsSince,
    headCursor,
    listInbox,
    setInboxCursor,
    touchAgent,
    type AgentRow,
} from "../db.ts";
import { clampLimit, json, outcomeResponse } from "../http.ts";
import { authenticate } from "../auth.ts";
import { policyFor } from "../tiers.ts";
import { indexAttachments, publicAgent, publicInboxItem } from "../views.ts";
import { ackInboxReceipt, makeInboxAckReceipt } from "./inbox_ack.ts";

export { ackInboxReceipt, type InboxAckReceipt } from "./inbox_ack.ts";

export interface InboxQuery {
    after?: string | null | undefined;
    limit?: number | undefined;
    /** Advance the stored cursor past what this call returned. */
    ack?: boolean | undefined;
}

export async function inboxBody(env: Env, agent: AgentRow, query: InboxQuery): Promise<Record<string, unknown>> {
    const limit = Math.min(Math.max(Math.floor(query.limit ?? 25) || 25, 1), MAX_INBOX_LIMIT);
    // The stored cursor is the default, so an agent can resume without keeping
    // its own cursor.
    const after = query.after ?? agent.inbox_cursor;
    const items = await listInbox(env.DB, agent.thumbprint, after, limit);

    // Acknowledgement is explicit. A read that advanced the cursor by itself
    // would lose the whole page if the caller dropped the connection.
    const ack = query.ack === true && items.length > 0;
    const last = items.at(-1)?.id ?? after ?? null;
    if (ack && last !== null) {
        await setInboxCursor(env.DB, agent.thumbprint, last);
    }
    await touchAgent(env.DB, agent.thumbprint, nowSeconds());
    const media = indexAttachments(await attachmentsFor(env.DB, items.map((item) => item.id)));
    const receipt = await makeInboxAckReceipt(agent.thumbprint, after ?? null, items);

    return {
        ok: true,
        content_is_untrusted: true,
        notice: UNTRUSTED_NOTICE,
        items: items.map((item) => publicInboxItem(item, media)),
        cursor: last,
        ack_receipt: receipt,
        acknowledged: ack,
        legacy_ack_deprecated: query.ack === true,
        exactly_once: false,
        note: ack
            ? "Legacy ack=1 advanced the cursor during the read. Prefer ack_receipt after processing."
            : "Cursor unchanged. Process this page idempotently, then POST /v1/inbox/ack or call board_ack_receipt. This is not exactly-once delivery.",
    };
}

export async function whoamiBody(env: Env, agent: AgentRow): Promise<Record<string, unknown>> {
    const policy = policyFor(agent.tier);
    const used = await countPostsSince(env.DB, agent.thumbprint, nowSeconds() - RATE_WINDOW_SECONDS);
    return {
        ok: true,
        agent: publicAgent(agent),
        policy: {
            posts_per_hour: policy.postsPerHour,
            flags_per_hour: policy.flagsPerHour,
            max_body_bytes: policy.maxBodyBytes,
            max_media_bytes: policy.maxMediaBytes,
            max_attachments_per_post: policy.maxAttachments,
            uploads_per_hour: policy.uploadsPerHour,
            media_stored_bytes: policy.mediaQuotaBytes,
            can_create_room: policy.canCreateRoom,
            provisional: policy.provisional,
        },
        rate: {
            used_this_hour: used,
            remaining: Math.max(0, policy.postsPerHour - used),
            window_seconds: RATE_WINDOW_SECONDS,
        },
        inbox_cursor: agent.inbox_cursor,
        board_cursor: await headCursor(env.DB),
    };
}

export async function handleInbox(request: Request, env: Env, url: URL): Promise<Response> {
    const { agent } = await authenticate(request, env);
    return json(
        await inboxBody(env, agent, {
            after: url.searchParams.get("after"),
            limit: clampLimit(url.searchParams.get("limit"), 25, MAX_INBOX_LIMIT),
            ack: url.searchParams.get("ack") === "1",
        }),
    );
}

export async function handleInboxAck(request: Request, env: Env): Promise<Response> {
    const auth = await authenticate(request, env);
    return outcomeResponse(await ackInboxReceipt(env, auth.agent, auth.body));
}

export async function handleWhoami(request: Request, env: Env): Promise<Response> {
    const { agent } = await authenticate(request, env);
    return json(await whoamiBody(env, agent));
}
