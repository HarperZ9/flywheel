/**
 * The MCP door.
 *
 * These run against the same board the HTTP checks ran against, because the
 * point of having two doors is that they cannot describe the board
 * differently. The last assertion here reads a post back over HTTP that was
 * written over MCP.
 */

import { BASE, check, send } from "./client.mjs";

/** Run the MCP checks. `agent` is a registered key with budget left to spend. */
async function mcpChecks(agent) {
    async function rpc(payload, agent) {
        if (agent === undefined) {
            const response = await fetch(`${BASE}/mcp`, {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify(payload),
            });
            return { status: response.status, body: await response.json().catch(() => null) };
        }
        return send(agent, "POST", "/mcp", payload);
    }

    const init = await rpc({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} });
    check("mcp initialize answers", init.body?.result?.protocolVersion === "2025-06-18", JSON.stringify(init.body));
    check("mcp names the server", init.body?.result?.serverInfo?.name === "bulletin");
    check(
        "mcp instructions warn about untrusted text",
        (init.body?.result?.instructions ?? "").includes("never as instructions"),
        JSON.stringify(init.body?.result?.instructions ?? "").slice(0, 200),
    );

    const tools = await rpc({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} });
    const listed = tools.body?.result?.tools ?? [];
    const names = listed.map((tool) => tool.name);
    check("mcp lists the read tools", names.includes("board_feed") && names.includes("board_search"), names.join(","));
    check("mcp lists the write tools", names.includes("board_write_post") && names.includes("board_whoami"));
    check("every mcp tool declares an input schema", listed.every((tool) => tool.inputSchema?.type === "object"));
    check(
        "a read tool is annotated read-only",
        listed.find((tool) => tool.name === "board_feed")?.annotations?.readOnlyHint === true,
    );

    const feedTool = await rpc({
        jsonrpc: "2.0",
        id: 3,
        method: "tools/call",
        params: { name: "board_feed", arguments: { room: "lobby", limit: 5 } },
    });
    check("an unsigned read tool works", feedTool.body?.result?.isError === false, JSON.stringify(feedTool.body).slice(0, 200));
    check("the tool result carries structured content", Array.isArray(feedTool.body?.result?.structuredContent?.posts));
    check("the tool result repeats the untrusted marker", feedTool.body?.result?.structuredContent?.content_is_untrusted === true);

    const unsignedWrite = await rpc({
        jsonrpc: "2.0",
        id: 4,
        method: "tools/call",
        params: { name: "board_write_post", arguments: { room: "lobby", body: "smoke: unsigned" } },
    });
    check(
        "an unsigned write tool is refused",
        unsignedWrite.body?.result?.isError === true,
        JSON.stringify(unsignedWrite.body).slice(0, 200),
    );
    check("the refusal names the code to branch on", unsignedWrite.body?.result?.structuredContent?.code === "unsigned");

    const signedWrite = await rpc(
        {
            jsonrpc: "2.0",
            id: 5,
            method: "tools/call",
            params: { name: "board_write_post", arguments: { room: "lobby", body: "smoke: posted over mcp" } },
        },
        agent,
    );
    check("a signed write tool posts", signedWrite.body?.result?.isError === false, JSON.stringify(signedWrite.body).slice(0, 300));
    const mcpPostId = signedWrite.body?.result?.structuredContent?.post?.id;
    check("the write answers with a post id", typeof mcpPostId === "string");
    if (typeof mcpPostId === "string") {
        const readBack = await (await fetch(`${BASE}/v1/posts/${mcpPostId}`)).json();
        check(
            "both doors describe the same post",
            readBack.post?.body === "smoke: posted over mcp",
            JSON.stringify(readBack).slice(0, 200),
        );
    }

    const unknownTool = await rpc({ jsonrpc: "2.0", id: 6, method: "tools/call", params: { name: "board_nope" } });
    check("an unknown tool is a protocol error", unknownTool.body?.error?.code === -32602, JSON.stringify(unknownTool.body));
    const batched = await rpc([{ jsonrpc: "2.0", id: 7, method: "ping" }]);
    check("a batch is refused by this protocol revision", batched.body?.error?.code === -32600, JSON.stringify(batched.body));
    const notification = await fetch(`${BASE}/mcp`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }),
    });
    check("a notification is acknowledged with no body", notification.status === 202, `got ${notification.status}`);
    const mcpGet = await fetch(`${BASE}/mcp`);
    check("GET on the mcp endpoint says which method to use", mcpGet.status === 405, `got ${mcpGet.status}`);
}

export { mcpChecks };
