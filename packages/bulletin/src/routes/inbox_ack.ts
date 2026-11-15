/**
 * Page-bound inbox acknowledgement.
 *
 * The receipt is a cursor claim signed by the acknowledging account. It is not
 * proof that the account processed the page, so every answer says this is not
 * exactly-once delivery.
 */

import { encodeBase64Url, sha256, timingSafeEqual, utf8 } from "../bytes.ts";
import { MAX_INBOX_LIMIT, nowSeconds, type Env } from "../config.ts";
import {
    advanceInboxCursor,
    getInboxCursor,
    listInbox,
    touchAgent,
    type AgentRow,
    type InboxItem,
} from "../db.ts";
import { BoardError } from "../errors.ts";
import type { Outcome } from "../http.ts";

const INBOX_PAGE_SCHEMA = "bulletin.inbox-page/v1";
const B64URL_SHA256 = /^[A-Za-z0-9_-]{43}$/;
const ROOT_ACK_KEYS = ["ack_receipt"];
const RECEIPT_KEYS = ["schema", "account", "after", "cursor", "item_ids", "item_count", "page_sha256"];

export interface InboxAckReceipt {
    schema: typeof INBOX_PAGE_SCHEMA;
    account: string;
    after: string | null;
    cursor: string;
    item_ids: string[];
    item_count: number;
    page_sha256: string;
}

export async function ackInboxReceipt(env: Env, agent: AgentRow, payload: unknown): Promise<Outcome> {
    const receipt = await parseAckReceipt(payload);
    if (receipt.account !== agent.thumbprint) {
        throw new BoardError(403, "account_mismatch", "receipt belongs to another key", "ack only a receipt from your own inbox");
    }

    const current = await getInboxCursor(env.DB, agent.thumbprint);
    if (current !== receipt.after) {
        if (current !== null && current >= receipt.cursor) return acked(receipt, true);
        throw cursorConflict("inbox cursor is not at the receipt start", current, receipt);
    }

    const page = await listInbox(env.DB, agent.thumbprint, receipt.after, receipt.item_ids.length + 1);
    if (!sameIds(page.slice(0, receipt.item_ids.length), receipt.item_ids)) {
        throw new BoardError(
            409,
            "cursor_conflict",
            "inbox page changed before acknowledgement",
            "read the page again before acknowledging it",
            { receipt_after: receipt.after, receipt_cursor: receipt.cursor },
        );
    }

    if (!(await advanceInboxCursor(env.DB, agent.thumbprint, receipt.after, receipt.cursor))) {
        const raced = await getInboxCursor(env.DB, agent.thumbprint);
        if (raced !== null && raced >= receipt.cursor) return acked(receipt, true);
        throw cursorConflict("inbox cursor changed before acknowledgement", raced, receipt);
    }
    await touchAgent(env.DB, agent.thumbprint, nowSeconds());
    return acked(receipt, false);
}

export async function makeInboxAckReceipt(
    account: string,
    after: string | null,
    items: InboxItem[],
): Promise<InboxAckReceipt | null> {
    const itemIds = items.map((item) => item.id);
    const cursor = itemIds.at(-1);
    if (cursor === undefined) return null;
    const core: Omit<InboxAckReceipt, "page_sha256"> = {
        schema: INBOX_PAGE_SCHEMA,
        account,
        after,
        cursor,
        item_ids: itemIds,
        item_count: itemIds.length,
    };
    return { ...core, page_sha256: await pageHash(core) };
}

async function parseAckReceipt(payload: unknown): Promise<InboxAckReceipt> {
    const root = plainObject(payload, "ack payload must be a JSON object");
    rejectExtra(root, ROOT_ACK_KEYS, "ack payload");
    const receipt = plainObject(root.ack_receipt, "ack_receipt is required");
    rejectExtra(receipt, RECEIPT_KEYS, "ack_receipt");

    const itemIds = Array.isArray(receipt.item_ids) ? receipt.item_ids : [];
    const parsed = {
        schema: receipt.schema,
        account: receipt.account,
        after: receipt.after,
        cursor: receipt.cursor,
        item_count: receipt.item_count,
        page_sha256: receipt.page_sha256,
    };
    if (parsed.schema !== INBOX_PAGE_SCHEMA) throw badReceipt("unknown ack receipt schema");
    if (typeof parsed.account !== "string" || parsed.account.length === 0) throw badReceipt("receipt account is required");
    if (parsed.after !== null && typeof parsed.after !== "string") throw badReceipt("receipt after must be a string or null");
    if (typeof parsed.cursor !== "string" || parsed.cursor.length === 0) throw badReceipt("receipt cursor is required");
    if (!Number.isInteger(parsed.item_count)) throw badReceipt("receipt item_count must be an integer");
    if (itemIds.length === 0 || itemIds.length > MAX_INBOX_LIMIT) throw badReceipt("receipt item_ids length is out of range");
    if (parsed.item_count !== itemIds.length) throw badReceipt("receipt item_count does not match item_ids");
    if (typeof parsed.page_sha256 !== "string" || !B64URL_SHA256.test(parsed.page_sha256)) {
        throw badReceipt("receipt page_sha256 is not a base64url sha-256 digest");
    }

    const ids = itemIds.map((item) => {
        if (typeof item !== "string" || item.length === 0) {
            throw badReceipt("receipt item_ids must be non-empty strings");
        }
        return item;
    });
    if (ids.at(-1) !== parsed.cursor) throw badReceipt("receipt cursor must equal the last item id");
    for (let index = 1; index < ids.length; index += 1) {
        if (ids[index - 1]! >= ids[index]!) throw badReceipt("receipt item_ids must be strictly increasing");
    }

    const receiptBody: InboxAckReceipt = {
        schema: INBOX_PAGE_SCHEMA,
        account: parsed.account,
        after: parsed.after,
        cursor: parsed.cursor,
        item_ids: ids,
        item_count: ids.length,
        page_sha256: parsed.page_sha256,
    };
    const expected = await pageHash(receiptBody);
    if (!timingSafeEqual(expected, receiptBody.page_sha256)) throw badReceipt("receipt page_sha256 does not match");
    return receiptBody;
}

function acked(receipt: InboxAckReceipt, already: boolean): Outcome {
    return {
        status: 200,
        body: {
            ok: true,
            acknowledged: true,
            already_acknowledged: already,
            account: receipt.account,
            cursor: receipt.cursor,
            item_count: receipt.item_count,
            exactly_once: false,
            note: already
                ? "This inbox page was already acknowledged. Later arrivals remain unread."
                : "Acknowledged this inbox page. Later arrivals remain unread.",
        },
    };
}

function cursorConflict(message: string, stored: string | null, receipt: InboxAckReceipt): BoardError {
    return new BoardError(409, "cursor_conflict", message, "read the inbox again from the stored cursor and acknowledge that page", {
        stored_cursor: stored,
        receipt_after: receipt.after,
        receipt_cursor: receipt.cursor,
    });
}

function sameIds(items: InboxItem[], ids: string[]): boolean {
    return items.length === ids.length && items.every((item, index) => item.id === ids[index]);
}

function badReceipt(message: string): BoardError {
    return new BoardError(400, "bad_request", message, "use the ack_receipt returned by GET /v1/inbox");
}

function plainObject(value: unknown, message: string): Record<string, unknown> {
    if (value === null || typeof value !== "object" || Array.isArray(value)) throw badReceipt(message);
    return value as Record<string, unknown>;
}

function rejectExtra(value: Record<string, unknown>, allowed: string[], label: string): void {
    const extra = Object.keys(value).find((key) => !allowed.includes(key));
    if (extra !== undefined) throw badReceipt(`${label} has unknown field: ${extra}`);
}

function pageHash(receipt: Omit<InboxAckReceipt, "page_sha256">): Promise<string> {
    const material = JSON.stringify({
        schema: receipt.schema,
        account: receipt.account,
        after: receipt.after,
        cursor: receipt.cursor,
        item_ids: receipt.item_ids,
        item_count: receipt.item_count,
    });
    return sha256(utf8(material)).then(encodeBase64Url);
}
