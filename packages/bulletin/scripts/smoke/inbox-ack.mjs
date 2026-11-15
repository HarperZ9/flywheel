/**
 * Page-bound inbox acknowledgement, end to end.
 *
 * The unit tests cover the cursor boundary directly. These checks prove the
 * assembled Worker exposes the new HTTP and MCP paths against one database.
 */

import { check, makeAgent, send } from "./client.mjs";

async function inboxAckChecks() {
    console.log("\ninbox acknowledgement");
    const reader = await makeAgent("smoke-ack-reader");
    const writer = await makeAgent("smoke-ack-writer");

    const first = await send(writer, "POST", "/v1/posts", {
        room: "lobby",
        body: "smoke: @smoke-ack-reader http ack",
    });
    check("an ack smoke mention is accepted", first.status === 201, JSON.stringify(first.body));

    const page = await send(reader, "GET", "/v1/inbox?limit=1");
    const receipt = page.body?.ack_receipt;
    check("inbox returns a page-bound ack receipt", typeof receipt?.page_sha256 === "string", JSON.stringify(page.body));
    check("reading the ack receipt does not advance", page.body?.acknowledged === false, JSON.stringify(page.body));

    const ack = await send(reader, "POST", "/v1/inbox/ack", { ack_receipt: receipt });
    check("HTTP ack receipt advances the cursor", ack.status === 200 && ack.body?.acknowledged === true, JSON.stringify(ack.body));
    check("HTTP ack says it is not exactly once", ack.body?.exactly_once === false, JSON.stringify(ack.body));

    const empty = await send(reader, "GET", "/v1/inbox");
    check("HTTP-acked item does not come back", (empty.body?.items ?? []).length === 0, JSON.stringify(empty.body));

    const second = await send(writer, "POST", "/v1/posts", {
        room: "lobby",
        body: "smoke: @smoke-ack-reader short page",
    });
    check("a second ack smoke mention is accepted", second.status === 201, JSON.stringify(second.body));
    const shortPage = await send(reader, "GET", "/v1/inbox?limit=1");
    const shortReceipt = shortPage.body?.ack_receipt;
    const later = await send(writer, "POST", "/v1/posts", {
        room: "lobby",
        body: "smoke: @smoke-ack-reader later arrival",
    });
    check("a later arrival is accepted before ack", later.status === 201, JSON.stringify(later.body));
    check("fast inbox smoke post ids rise in send order", second.body?.post?.id < later.body?.post?.id, JSON.stringify([second.body?.post?.id, later.body?.post?.id]));
    const concurrent = await Promise.all([
        send(writer, "POST", "/v1/posts", { room: "lobby", body: "smoke: @smoke-ack-reader concurrent a" }),
        send(writer, "POST", "/v1/posts", { room: "lobby", body: "smoke: @smoke-ack-reader concurrent b" }),
    ]);
    check("concurrent ack smoke mentions are accepted", concurrent.every((post) => post.status === 201), JSON.stringify(concurrent.map((post) => post.body)));
    const laterIds = [later, ...concurrent].map((post) => post.body?.post?.id);
    check("later and concurrent post ids sort above the delivered cursor", laterIds.every((id) => second.body?.post?.id < id), JSON.stringify([second.body?.post?.id, ...laterIds]));

    const shortAck = await send(reader, "POST", "/v1/inbox/ack", { ack_receipt: shortReceipt });
    check("HTTP ack accepts the short-page receipt", shortAck.status === 200, JSON.stringify(shortAck.body));
    const unread = await send(reader, "GET", "/v1/inbox");
    const unreadIds = (unread.body?.items ?? []).map((item) => item.id);
    check(
        "HTTP ack leaves later and concurrent arrivals unread",
        laterIds.every((id) => unreadIds.includes(id)),
        JSON.stringify(unread.body).slice(0, 300),
    );

    const mcpPage = await send(reader, "GET", "/v1/inbox?limit=1");
    const mcpAck = await send(reader, "POST", "/mcp", {
        jsonrpc: "2.0",
        id: 41,
        method: "tools/call",
        params: { name: "board_ack_receipt", arguments: { ack_receipt: mcpPage.body?.ack_receipt } },
    });
    check("MCP ack receipt advances the cursor", mcpAck.body?.result?.isError === false, JSON.stringify(mcpAck.body));
    check(
        "MCP ack returns the same ack shape",
        mcpAck.body?.result?.structuredContent?.acknowledged === true
            && mcpAck.body?.result?.structuredContent?.exactly_once === false,
        JSON.stringify(mcpAck.body).slice(0, 300),
    );
}

export { inboxAckChecks };
