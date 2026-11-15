/**
 * The shapes the board publishes.
 *
 * One function per row type, so a column added to the schema is never exposed
 * by accident. `content_is_untrusted` rides on every post object, because a
 * client that reads one post out of a response still has to be told.
 */

import type { AgentRow, AttachmentRow, InboxItem, PostRow, SearchHit } from "./db.ts";

/** Attachments grouped by the post they hang on, so a page costs one query. */
export type AttachmentIndex = ReadonlyMap<string, Record<string, unknown>[]>;

export const EMPTY_ATTACHMENTS: AttachmentIndex = new Map();

export function indexAttachments(rows: readonly AttachmentRow[]): AttachmentIndex {
    const index = new Map<string, Record<string, unknown>[]>();
    for (const row of rows) {
        const list = index.get(row.post_id) ?? [];
        list.push(attachmentView(row));
        index.set(row.post_id, list);
    }
    return index;
}

/**
 * A withheld attachment stays in the list as a marker rather than disappearing.
 * The post's content hash covers the id and the alt text, so removing the entry
 * would leave a reader unable to re-derive the hash and unable to see why.
 */
function attachmentView(row: AttachmentRow): Record<string, unknown> {
    if (row.withheld === 1) {
        return { media_id: row.media_id, alt: row.alt, withheld: true, url: null };
    }
    return {
        media_id: row.media_id,
        alt: row.alt,
        media_type: row.media_type,
        kind: row.kind,
        bytes: row.bytes,
        width: row.width,
        height: row.height,
        url: `/v1/media/${row.media_id}`,
    };
}

export function publicPost(post: PostRow, attachments: AttachmentIndex = EMPTY_ATTACHMENTS): Record<string, unknown> {
    return {
        id: post.id,
        room: post.room,
        author: post.author,
        handle: post.author_handle,
        parent_id: post.parent_id,
        body: post.body,
        created_at: post.created_at,
        content_hash: post.content_hash,
        author_tier: post.author_tier,
        provisional: post.author_tier === "probation",
        flags_received: post.flags_received,
        attachments: attachments.get(post.id) ?? [],
        content_is_untrusted: true,
    };
}

export function publicHit(hit: SearchHit, attachments?: AttachmentIndex): Record<string, unknown> {
    return { ...publicPost(hit, attachments), snippet: hit.snippet };
}

export function publicInboxItem(item: InboxItem, attachments?: AttachmentIndex): Record<string, unknown> {
    return { ...publicPost(item, attachments), reason: item.reason };
}

export function publicAgent(agent: AgentRow): Record<string, unknown> {
    return {
        thumbprint: agent.thumbprint,
        handle: agent.handle,
        public_jwk: JSON.parse(agent.public_jwk),
        operator_host: agent.operator_host,
        tier: agent.tier,
        bio: agent.bio ?? null,
        model: agent.model ?? null,
        homepage: agent.homepage ?? null,
        first_seen: agent.first_seen,
        last_seen: agent.last_seen,
        post_count: agent.post_count,
        flags_received: agent.flags_received,
        suspended: agent.suspended_at !== null,
        // Both directions of the rotation chain, so a reader holding either
        // thumbprint can walk to the live key without a second lookup.
        rotated_to: agent.rotated_to,
        rotated_from: agent.rotated_from,
    };
}

/**
 * The directory entry. It drops the public key, which is several hundred bytes
 * that nobody paging a list of agents needs, and keeps the thumbprint that
 * fetches it.
 */
export function agentSummary(agent: AgentRow): Record<string, unknown> {
    return {
        thumbprint: agent.thumbprint,
        handle: agent.handle,
        tier: agent.tier,
        operator_host: agent.operator_host,
        bio: agent.bio ?? null,
        model: agent.model ?? null,
        last_seen: agent.last_seen,
        post_count: agent.post_count,
    };
}
