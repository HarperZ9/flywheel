import assert from "node:assert/strict";
import { test } from "node:test";

import { BoardError } from "../src/errors.ts";
import { ackInboxReceipt, inboxBody, type InboxAckReceipt } from "../src/routes/inbox.ts";
import { listTools } from "../src/tools.ts";
import worker, { type Env } from "../src/worker.ts";
import { makeSigner, signRequest, type Signer } from "./helpers.ts";
import { agent, envWith, InboxDb, OTHER, RECEIVER } from "./inbox-ack-helpers.ts";

const ctx = { waitUntil: () => {}, passThroughOnException: () => {} } as unknown as ExecutionContext;

async function page(db: InboxDb, account = RECEIVER, limit = 25, after?: string): Promise<InboxAckReceipt> {
    const owner = db.agents.get(account);
    assert.ok(owner, `missing test account ${account}`);
    const body = await inboxBody(envWith(db), owner as never, { after, limit, ack: false });
    return body.ack_receipt as InboxAckReceipt;
}

test("inbox read returns a page-bound receipt without advancing the cursor", async () => {
    const db = new InboxDb();
    db.addAgent(agent());
    db.addInboxPost("p001");
    db.addInboxPost("p002");

    const body = await inboxBody(envWith(db), db.agents.get(RECEIVER)! as never, { limit: 2, ack: false });
    const receipt = body.ack_receipt as InboxAckReceipt;

    assert.equal(body.acknowledged, false);
    assert.equal(db.cursor(RECEIVER), null);
    assert.equal(receipt.schema, "bulletin.inbox-page/v1");
    assert.equal(receipt.account, RECEIVER);
    assert.equal(receipt.after, null);
    assert.equal(receipt.cursor, "p002");
    assert.deepEqual(receipt.item_ids, ["p001", "p002"]);
    assert.equal(receipt.item_count, 2);
    assert.match(receipt.page_sha256, /^[A-Za-z0-9_-]{43}$/);
});

test("ack advances only through the delivered cursor when a new item arrives after the page", async () => {
    const db = new InboxDb();
    db.addAgent(agent());
    db.addInboxPost("p001");
    const receipt = await page(db, RECEIVER, 1);
    db.addInboxPost("p002");

    const outcome = await ackInboxReceipt(envWith(db), db.agents.get(RECEIVER)! as never, { ack_receipt: receipt });

    assert.equal(outcome.status, 200);
    assert.equal(db.cursor(RECEIVER), "p001");
    assert.deepEqual(outcome.body, {
        ok: true,
        acknowledged: true,
        already_acknowledged: false,
        account: RECEIVER,
        cursor: "p001",
        item_count: 1,
        exactly_once: false,
        note: "Acknowledged this inbox page. Later arrivals remain unread.",
    });
    const next = await inboxBody(envWith(db), db.agents.get(RECEIVER)! as never, { ack: false });
    assert.deepEqual((next.items as Array<{ id: string }>).map((item) => item.id), ["p002"]);
});

test("ack replay and parallel same-page consumers are idempotent", async () => {
    const db = new InboxDb();
    db.addAgent(agent());
    db.addInboxPost("p001");
    const receipt = await page(db);

    const first = await ackInboxReceipt(envWith(db), db.agents.get(RECEIVER)! as never, { ack_receipt: receipt });
    const second = await ackInboxReceipt(envWith(db), db.agents.get(RECEIVER)! as never, { ack_receipt: receipt });

    assert.equal(db.cursor(RECEIVER), "p001");
    assert.equal(first.body.already_acknowledged, false);
    assert.equal(second.body.already_acknowledged, true);
    assert.equal(second.body.acknowledged, true);
});

test("ack refuses an interleaving cursor advance to an intermediate item", async () => {
    const db = new InboxDb();
    db.addAgent(agent());
    db.addInboxPost("p001");
    db.addInboxPost("p002");
    const receipt = await page(db, RECEIVER, 2);
    db.beforeCursorUpdate = () => {
        db.agents.get(RECEIVER)!.inbox_cursor = "p001";
    };

    await assert.rejects(
        ackInboxReceipt(envWith(db), db.agents.get(RECEIVER)! as never, { ack_receipt: receipt }),
        (error) => error instanceof BoardError && error.status === 409 && error.code === "cursor_conflict",
    );
    assert.equal(db.cursor(RECEIVER), "p001");
});

test("ack replay after a later page never moves the cursor back", async () => {
    const db = new InboxDb();
    db.addAgent(agent());
    db.addInboxPost("p001");
    db.addInboxPost("p002");
    const first = await page(db, RECEIVER, 1);
    await ackInboxReceipt(envWith(db), db.agents.get(RECEIVER)! as never, { ack_receipt: first });
    const second = await page(db, RECEIVER, 1);
    await ackInboxReceipt(envWith(db), db.agents.get(RECEIVER)! as never, { ack_receipt: second });

    const replayed = await ackInboxReceipt(envWith(db), db.agents.get(RECEIVER)! as never, { ack_receipt: first });

    assert.equal(replayed.body.already_acknowledged, true);
    assert.equal(db.cursor(RECEIVER), "p002");
});

test("ack refuses skip-ahead when stored cursor has not reached receipt after", async () => {
    const db = new InboxDb();
    db.addAgent(agent());
    db.addInboxPost("p001");
    db.addInboxPost("p002");
    const receipt = await page(db, RECEIVER, 1, "p001");

    await assert.rejects(
        ackInboxReceipt(envWith(db), db.agents.get(RECEIVER)! as never, { ack_receipt: receipt }),
        (error) => error instanceof BoardError && error.status === 409 && error.code === "cursor_conflict",
    );
    assert.equal(db.cursor(RECEIVER), null);
});

test("ack rejects extra fields at the root and inside the receipt", async () => {
    const cases = [
        (receipt: InboxAckReceipt) => ({ ack_receipt: receipt, extra: true }),
        (receipt: InboxAckReceipt) => ({ ack_receipt: { ...receipt, extra: true } }),
    ];
    for (const payload of cases) {
        const db = new InboxDb();
        db.addAgent(agent());
        db.addInboxPost("p001");
        const receipt = await page(db);

        await assert.rejects(
            ackInboxReceipt(envWith(db), db.agents.get(RECEIVER)! as never, payload(receipt)),
            (error) => error instanceof BoardError && error.status === 400 && error.code === "bad_request",
        );
        assert.equal(db.cursor(RECEIVER), null);
    }
});

test("ack refuses a tampered page receipt", async () => {
    const db = new InboxDb();
    db.addAgent(agent());
    db.addInboxPost("p001");
    const receipt = await page(db);
    const tampered = { ...receipt, cursor: "p999", item_ids: ["p999"] };

    await assert.rejects(
        ackInboxReceipt(envWith(db), db.agents.get(RECEIVER)! as never, { ack_receipt: tampered }),
        (error) => error instanceof BoardError && error.status === 400 && error.code === "bad_request",
    );
    assert.equal(db.cursor(RECEIVER), null);
});

test("ack refuses a page whose delivered rows are no longer visible", async () => {
    const db = new InboxDb();
    db.addAgent(agent());
    db.addInboxPost("p001");
    const receipt = await page(db);
    db.posts[0]!.withheld = 1;

    await assert.rejects(
        ackInboxReceipt(envWith(db), db.agents.get(RECEIVER)! as never, { ack_receipt: receipt }),
        (error) => error instanceof BoardError && error.status === 409 && error.code === "cursor_conflict",
    );
    assert.equal(db.cursor(RECEIVER), null);
});

test("signed HTTP ack rejects non-object JSON bodies as bad_request", async () => {
    const signer = await makeSigner();
    const world = await worldFor(signer);
    const bodies = ["null", "[]", "42"];

    for (const [index, body] of bodies.entries()) {
        const response = await callSignedAckRaw(signer, world.db, body, `http-bad-${index}`);
        assert.equal(response.status, 400);
        assert.equal(response.body.code, "bad_request");
    }
});

test("ack is bound to the signing account", async () => {
    const db = new InboxDb();
    db.addAgent(agent(RECEIVER));
    db.addAgent(agent(OTHER));
    db.addInboxPost("p001");
    const receipt = await page(db);

    await assert.rejects(
        ackInboxReceipt(envWith(db), db.agents.get(OTHER)! as never, { ack_receipt: receipt }),
        (error) => error instanceof BoardError && error.status === 403 && error.code === "account_mismatch",
    );
    assert.equal(db.cursor(RECEIVER), null);
    assert.equal(db.cursor(OTHER), null);
});

test("HTTP and MCP expose the same acknowledgement core", async () => {
    const signer = await makeSigner();
    const http = await callSignedAck(signer, await worldFor(signer));
    const mcp = await callSignedAckTool(signer, await worldFor(signer));
    const tool = listTools().find((entry) => entry.name === "board_ack_receipt");

    assert.equal(tool?.signed, true);
    assert.equal(tool?.readOnly, false);
    assert.equal(tool?.idempotent, true);
    assert.deepEqual(mcp, http);
});

test("MCP ack rejects schema-extra receipt fields at runtime", async () => {
    const signer = await makeSigner();
    const world = await worldFor(signer);
    const response = await callSignedAckToolRaw(
        signer,
        world.db,
        { ack_receipt: { ...world.receipt, extra: true } },
        "mcp-extra",
    );

    assert.equal(response.result.isError, true);
    assert.equal(response.result.structuredContent.code, "bad_request");
});

test("MCP ack rejects non-object arguments as bad_request", async () => {
    const signer = await makeSigner();
    const world = await worldFor(signer);
    const args = [null, [], 42];

    for (const [index, value] of args.entries()) {
        const response = await callSignedAckToolRaw(signer, world.db, value, `mcp-bad-${index}`);
        assert.equal(response.result.isError, true);
        assert.equal(response.result.structuredContent.code, "bad_request");
    }
});

async function worldFor(signer: Signer): Promise<{ db: InboxDb; receipt: InboxAckReceipt }> {
    const db = new InboxDb();
    db.addAgent(agent(signer.thumbprint, JSON.stringify(signer.jwk)));
    db.addInboxPost("p001", signer.thumbprint);
    return { db, receipt: await page(db, signer.thumbprint) };
}

async function callSignedAck(signer: Signer, world: { db: InboxDb; receipt: InboxAckReceipt }): Promise<Record<string, unknown>> {
    const body = JSON.stringify({ ack_receipt: world.receipt });
    const response = await callSignedAckRaw(signer, world.db, body, "http-ack");
    assert.equal(response.status, 200);
    return response.body;
}

async function callSignedAckRaw(
    signer: Signer,
    db: InboxDb,
    body: string,
    nonce: string,
): Promise<{ status: number; body: Record<string, any> }> {
    const request = await signRequest(signer, {
        method: "POST",
        url: "https://board.example/v1/inbox/ack",
        body,
        nonce,
    });
    const response = await worker.fetch(request, envWith(db), ctx);
    return { status: response.status, body: await response.json() as Record<string, any> };
}

async function callSignedAckTool(signer: Signer, world: { db: InboxDb; receipt: InboxAckReceipt }): Promise<Record<string, unknown>> {
    const rpc = await callSignedAckToolRaw(signer, world.db, { ack_receipt: world.receipt }, "mcp-ack");
    assert.equal(rpc.result.isError, false);
    return rpc.result.structuredContent;
}

async function callSignedAckToolRaw(
    signer: Signer,
    db: InboxDb,
    args: unknown,
    nonce: string,
): Promise<Record<string, any>> {
    const body = JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "tools/call",
        params: { name: "board_ack_receipt", arguments: args },
    });
    const request = await signRequest(signer, {
        method: "POST",
        url: "https://board.example/mcp",
        body,
        nonce,
    });
    const response = await worker.fetch(request, envWith(db), ctx);
    assert.equal(response.status, 200);
    return response.json() as Promise<Record<string, any>>;
}
