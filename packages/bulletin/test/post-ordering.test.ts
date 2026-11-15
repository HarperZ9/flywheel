import assert from "node:assert/strict";
import test from "node:test";
import { createPost } from "../src/routes/posts.ts";
import { ackInboxReceipt, makeInboxAckReceipt } from "../src/routes/inbox_ack.ts";
import { insertPost, listInbox } from "../src/db.ts";
import type { AuthenticatedRequest } from "../src/auth.ts";
import { agent, OTHER, RECEIVER } from "./inbox-ack-helpers.ts";
import { envWith, HIGH_ID, LOW_ID, OrderingDb, withFixedRandomBytes, writeMention } from "./post-ordering-helpers.ts";

test("same-second posts keep insertion order when an inbox page is acknowledged", async () => {
    const db = new OrderingDb();
    db.addAgent(agent(RECEIVER));
    db.addAgent(agent(OTHER));
    db.spendNonce("n1");
    db.spendNonce("n2");

    const firstId = await writeMention(db, HIGH_ID, "n1");
    db.addMention(firstId, RECEIVER);
    const firstPage = await listInbox(db as unknown as D1Database, RECEIVER, null, 1);
    const receipt = await makeInboxAckReceipt(RECEIVER, null, firstPage);
    await ackInboxReceipt(envWith(db), db.agents.get(RECEIVER)! as never, { ack_receipt: receipt });

    const secondId = await writeMention(db, LOW_ID, "n2");
    db.addMention(secondId, RECEIVER);
    assert.ok(firstId < secondId, "later same-second post must sort after the acknowledged cursor");
    const unread = await listInbox(db as unknown as D1Database, RECEIVER, db.cursor(RECEIVER), 10);
    assert.deepEqual(unread.map((item) => item.id), [secondId]);
});

test("post creation makes a mention visible in the same commit as the post", async () => {
    const db = new OrderingDb();
    const receiver = agent(RECEIVER);
    receiver.handle = "reader";
    db.addAgent(receiver);
    db.addAgent(agent(OTHER));
    db.spendNonce("writer-post");

    db.afterPostOnlyBatch = async () => {
        db.addInboxPost(HIGH_ID, RECEIVER);
        const page = await listInbox(db as unknown as D1Database, RECEIVER, null, 1);
        const receipt = await makeInboxAckReceipt(RECEIVER, null, page);
        await ackInboxReceipt(envWith(db), db.agents.get(RECEIVER)! as never, { ack_receipt: receipt });
    };

    const outcome = await withFixedRandomBytes(0, () =>
        createPost(
            envWith(db),
            { waitUntil: (promise: Promise<unknown>) => void promise.catch(() => {}) } as unknown as ExecutionContext,
            { agent: db.agents.get(OTHER)!, nonceKey: "writer-post" } as AuthenticatedRequest,
            { room: "lobby", body: "hello @reader" },
            "sig",
        ),
    );

    const post = outcome.body.post as { id: string };
    const unread = await listInbox(db as unknown as D1Database, RECEIVER, db.cursor(RECEIVER), 10);
    assert.ok(unread.some((item) => item.id === post.id), "the created mention must not vanish behind another ack");
});

test("post insertion refuses a missing nonce before touching counters", async () => {
    const db = new OrderingDb();
    db.addAgent(agent(OTHER));

    await assert.rejects(writeMention(db, LOW_ID, "missing"), /post insert did not allocate an id/);
    assert.equal(db.posts.length, 0);
    assert.equal(db.agents.get(OTHER)!.post_count, 0);
    assert.equal(db.rooms.get("lobby")!.post_count, 0);
});

test("post insertion refuses an already recorded nonce before touching counters", async () => {
    const db = new OrderingDb();
    db.addAgent(agent(OTHER));
    db.recordNonce("used", "post", HIGH_ID);

    await assert.rejects(writeMention(db, LOW_ID, "used"), /post insert did not allocate an id/);
    assert.equal(db.posts.length, 0);
    assert.equal(db.agents.get(OTHER)!.post_count, 0);
    assert.equal(db.rooms.get("lobby")!.post_count, 0);
});

test("post insertion rolls back nonce results and counters when the post insert fails", async () => {
    const db = new OrderingDb();
    db.addAgent(agent(OTHER));
    db.spendNonce("will-fail");
    db.failNextPostInsert = true;

    await assert.rejects(writeMention(db, LOW_ID, "will-fail"), /post insert failed/);
    assert.deepEqual(db.spent.get("will-fail"), { result_kind: null, result_id: null });
    assert.equal(db.posts.length, 0);
    assert.equal(db.mentions.length, 0);
    assert.equal(db.agents.get(OTHER)!.post_count, 0);
    assert.equal(db.rooms.get("lobby")!.post_count, 0);
});