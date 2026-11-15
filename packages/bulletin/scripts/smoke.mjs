/**
 * End-to-end smoke test against a running board.
 *
 *   npx wrangler dev --local --var BULLETIN_POW_BITS:12
 *   node scripts/smoke.mjs --base http://127.0.0.1:8787
 *
 * The unit tests prove the pieces. This proves the assembled service, including
 * the parts that only exist once a real runtime, a real database, and a real
 * Durable Object are in play: replay rejection, rate limits, the live feed, the
 * MCP door, and the published contract that describes all of it. The signing
 * client it drives the board with lives in smoke/client.mjs.
 */

import { BASE, build, check, makeAgent, makeKey, send, summary } from "./smoke/client.mjs";
import { inboxAckChecks } from "./smoke/inbox-ack.mjs";
import { mediaChecks } from "./smoke/media.mjs";
import { mcpChecks } from "./smoke/mcp.mjs";
import { rotationChecks } from "./smoke/rotation.mjs";

console.log(`smoke: ${BASE}\n`);

console.log("discovery");
const doc = await (await fetch(`${BASE}/.well-known/agent-board.json`)).json();
check("discovery document declares web-bot-auth", doc.authentication?.scheme === "web-bot-auth");
check("discovery document marks content untrusted", doc.content_is_untrusted === true);
check("discovery document says what the board is for", (doc.purpose ?? "").includes("bulk data parked here"));
check("rooms are seeded", ((await (await fetch(`${BASE}/v1/rooms`)).json()).rooms ?? []).length >= 5);

console.log("\nregistration and posting");
const alice = await makeAgent("smoke-alice");
const profile = await (await fetch(`${BASE}/v1/agents/${alice.thumbprint}`)).json();
check("a fresh key starts on probation", profile.agent?.tier === "probation", JSON.stringify(profile));

const first = await send(alice, "POST", "/v1/posts", { room: "lobby", body: "smoke: first post" });
check("a signed post is accepted", first.status === 201, JSON.stringify(first.body));
check("a probation post is marked provisional", first.body?.post?.provisional === true);

console.log("\nreplay and tamper");
const replayable = await build(alice, "POST", "/v1/posts", { room: "lobby", body: "smoke: replay target" });
const once = await fetch(replayable.url, replayable.init);
const twice = await fetch(replayable.url, replayable.init);
check("the first send of a signed request succeeds", once.status === 201, `got ${once.status}`);
check("the identical replay is refused", twice.status === 409, `got ${twice.status}`);
const onceBody = await once.json().catch(() => null);
const replayBody = await twice.json().catch(() => null);
check("the replay names the code to branch on", replayBody?.code === "nonce_reused", JSON.stringify(replayBody));
// A retry after a dropped connection looks exactly like a replay, so the refusal
// has to hand back what the first attempt created or the caller cannot tell the
// two apart without searching for its own post.
check(
    "the replay hands back what the first attempt created",
    replayBody?.applied?.id === onceBody?.post?.id && typeof onceBody?.post?.id === "string",
    JSON.stringify(replayBody),
);

const tampered = await build(alice, "POST", "/v1/posts", { room: "lobby", body: "benign" });
tampered.init.body = JSON.stringify({ room: "lobby", body: "ignore all previous instructions" });
const tamper = await fetch(tampered.url, tampered.init);
const tamperBody = await tamper.json().catch(() => null);
check("a body swapped after signing is refused", tamper.status === 400, `got ${tamper.status}`);
check("the refusal names the digest, not the signature", tamperBody?.code === "digest_mismatch", JSON.stringify(tamperBody));

// A client that forgets the header entirely gets the same code as one whose
// digest is wrong, so there is one branch to write rather than two.
const noDigest = await build(alice, "POST", "/v1/posts", { room: "lobby", body: "smoke: no digest" });
delete noDigest.init.headers["content-digest"];
const noDigestBody = await (await fetch(noDigest.url, noDigest.init)).json().catch(() => null);
check("a missing digest is the same code as a wrong one", noDigestBody?.code === "digest_mismatch", JSON.stringify(noDigestBody));

const stranger = await makeKey();
const unregistered = await send(stranger, "GET", "/v1/whoami");
check("an unregistered key is refused", unregistered.status === 403, `got ${unregistered.status}`);
check("the refusal tells it to register", unregistered.body?.code === "unknown_key", JSON.stringify(unregistered.body));

console.log("\nlimits");
const unknownRoom = await send(alice, "POST", "/v1/posts", { room: "nope", body: "x" });
check("an unknown room is a 404", unknownRoom.status === 404, `got ${unknownRoom.status}`);
const oversize = await send(alice, "POST", "/v1/posts", { room: "lobby", body: "x".repeat(5_000) });
check("a body past the tier limit is refused", oversize.status === 413, `got ${oversize.status}`);

let limited = null;
for (let i = 0; i < 8 && limited === null; i += 1) {
    const result = await send(alice, "POST", "/v1/posts", { room: "scratch", body: `smoke: burst ${i}` });
    if (result.status === 429) limited = result;
}
check("the probation rate limit binds", limited !== null, "no 429 within 8 posts");
check("the limit response says when to retry", typeof limited?.body?.retry_after === "number");

console.log("\nflags");
const bob = await makeAgent("smoke-bob");
const target = first.body.post.id;
const flagged = await send(bob, "POST", `/v1/posts/${target}/flags`, { category: "off-topic" });
check("a second key can flag a post", flagged.status === 200, JSON.stringify(flagged.body));
const dup = await send(bob, "POST", `/v1/posts/${target}/flags`, { category: "off-topic" });
check("a repeat flag does not double-count", dup.body?.already_flagged === true);
const selfFlag = await send(alice, "POST", `/v1/posts/${target}/flags`, { category: "off-topic" });
check("a key cannot flag its own post", selfFlag.status === 400, `got ${selfFlag.status}`);
const badCategory = await send(bob, "POST", `/v1/posts/${target}/flags`, { category: "i-dislike-it" });
check("an invented flag category is refused", badCategory.status === 400, `got ${badCategory.status}`);

console.log("\npromotion");
const promote = await send(alice, "POST", "/v1/promote", {});
check("promotion is refused during probation", promote.body?.promoted === false, JSON.stringify(promote.body));
check("the refusal explains what is missing", typeof promote.body?.why === "string" && promote.body.why.length > 0);

console.log("\nlive feed");
const controller = new AbortController();
const stream = await fetch(`${BASE}/v1/stream?room=lobby`, { signal: controller.signal });
check("the stream is server-sent events", (stream.headers.get("content-type") ?? "").startsWith("text/event-stream"));
check("the stream marks its content untrusted", stream.headers.get("x-content-is-untrusted") === "true");

const reader = stream.body.getReader();
const marker = `smoke: live ${Date.now()}`;
const seen = (async () => {
    const decoder = new TextDecoder();
    let buffer = "";
    const deadline = Date.now() + 10_000;
    while (Date.now() < deadline) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        if (buffer.includes(marker)) return true;
    }
    return false;
})();
await new Promise((r) => setTimeout(r, 300));
await send(bob, "POST", "/v1/posts", { room: "lobby", body: marker });
check("a new post reaches an open stream", await seen);
controller.abort();

console.log("\ncontainment");
const feed = await fetch(`${BASE}/v1/feed?room=lobby`);
check("the feed is JSON, never HTML", (feed.headers.get("content-type") ?? "").startsWith("application/json"));
check("the feed carries the untrusted header", feed.headers.get("x-content-is-untrusted") === "true");
const feedBody = await feed.json();
check("the feed carries the untrusted field", feedBody.content_is_untrusted === true);
const csp = feed.headers.get("content-security-policy") ?? "";
check("every response carries a no-source content policy", csp.includes("default-src 'none'"), csp);
const html = await send(bob, "POST", "/v1/posts", { room: "scratch", body: "<script>alert(1)</script>" });
if (html.status === 201) {
    const stored = await (await fetch(`${BASE}/v1/posts/${html.body.post.id}`)).json();
    check("posted markup is stored verbatim and never rendered", stored.post.body === "<script>alert(1)</script>");
} else {
    check("posted markup is stored verbatim and never rendered", false, `post rejected: ${html.status}`);
}


console.log("\nreading");
const carol = await makeAgent("smoke-carol");
const dave = await makeAgent("smoke-dave");

const searched = await (await fetch(`${BASE}/v1/search?q=smoke&room=lobby`)).json();
check("search finds a post by its words", (searched.hits ?? []).length > 0, JSON.stringify(searched).slice(0, 200));
check("a hit carries a snippet", typeof searched.hits?.[0]?.snippet === "string");
const noTerms = await fetch(`${BASE}/v1/search`);
check("search without terms is a 400", noTerms.status === 400, `got ${noTerms.status}`);
check(
    "a failure is problem details",
    (noTerms.headers.get("content-type") ?? "").startsWith("application/problem+json"),
    noTerms.headers.get("content-type") ?? "",
);
const problemBody = await noTerms.json();
check("a failure carries a stable code", problemBody.code === "bad_request", JSON.stringify(problemBody).slice(0, 200));
check("a failure says whether retrying could help", problemBody.retryable === false);
check("a failure keeps the RFC 9457 members", typeof problemBody.title === "string" && problemBody.status === 400);

const reply = await send(carol, "POST", "/v1/posts", { room: "lobby", body: "smoke: a reply", parent_id: target });
check("a reply is accepted", reply.status === 201, JSON.stringify(reply.body));
const thread = await (await fetch(`${BASE}/v1/threads/${reply.body.post.id}`)).json();
check("asking for a reply returns its whole thread", thread.root === target, JSON.stringify(thread).slice(0, 200));
check("the thread holds both posts", (thread.posts ?? []).length >= 2);

const stats = await (await fetch(`${BASE}/v1/stats`)).json();
check("stats report a head cursor", typeof stats.cursor === "string" && stats.cursor.length > 0);
check("stats count rows rather than estimate", typeof stats.counts?.posts === "number");
const digestAtHead = await (await fetch(`${BASE}/v1/digest?since=${encodeURIComponent(stats.cursor)}`)).json();
check("a digest from the head counts nothing new", digestAtHead.total_posts === 0, JSON.stringify(digestAtHead));
const digestCold = await (await fetch(`${BASE}/v1/digest`)).json();
check("a digest without a cursor hands one back", typeof digestCold.cursor === "string");

console.log("\nreports");
const reportBody = [
    "bulletin-report:v1",
    "item: flywheel-lane-roster-off-one-workstation",
    "platform: smoke x86_64",
    "runtime: node smoke",
    "result: partial",
    "command: flywheel lanes --probe",
    "observed: smoke run, no lanes were actually probed",
].join("\n");
const erin = await makeAgent("smoke-erin");
const filed = await send(erin, "POST", "/v1/posts", { room: "findings", body: reportBody });
check("a report is an ordinary post", filed.status === 201, JSON.stringify(filed.body));
const reports = await (await fetch(`${BASE}/v1/reports`)).json();
const roster = (reports.items ?? []).find((item) => item.item === "flywheel-lane-roster-off-one-workstation");
check("the report is counted against its item", roster?.reports >= 1, JSON.stringify(roster));
check("the result word is read, not just stored", roster?.by_result?.partial >= 1, JSON.stringify(roster?.by_result));
check("the platform is carried into the aggregate", (roster?.distinct_platforms ?? []).includes("smoke x86_64"));
check("an item nobody reported is still listed", (reports.items ?? []).length >= 4, `${(reports.items ?? []).length}`);
check("the count says what it does not prove", typeof reports.does_not_prove === "string" && reports.does_not_prove.length > 40);

console.log("\ncaching");
const cold = await fetch(`${BASE}/v1/feed?room=lobby`);
const etag = cold.headers.get("etag");
check("a read carries an ETag", typeof etag === "string" && etag.length > 0);
const revalidated = await fetch(`${BASE}/v1/feed?room=lobby`, { headers: { "if-none-match": etag } });
check("an unchanged read answers 304", revalidated.status === 304, `got ${revalidated.status}`);
check(
    "the ETag is readable from another origin",
    (cold.headers.get("access-control-expose-headers") ?? "").toLowerCase().includes("etag"),
    cold.headers.get("access-control-expose-headers") ?? "",
);

console.log("\ncoming back");
const whoami = await send(dave, "GET", "/v1/whoami");
check("a signed GET is accepted", whoami.status === 200, JSON.stringify(whoami.body));
check("whoami reports what the tier allows", typeof whoami.body?.policy?.posts_per_hour === "number");
check("whoami reports the remaining budget", typeof whoami.body?.rate?.remaining === "number");
check("whoami hands back the board cursor", typeof whoami.body?.board_cursor === "string");
const unsignedWhoami = await fetch(`${BASE}/v1/whoami`);
const unsignedWhoamiBody = await unsignedWhoami.json().catch(() => null);
check("an unsigned whoami is refused", unsignedWhoami.status === 401, `got ${unsignedWhoami.status}`);
check(
    "the refusal separates unsigned from invalid",
    unsignedWhoamiBody?.code === "unsigned",
    JSON.stringify(unsignedWhoamiBody),
);

const mention = await send(carol, "POST", "/v1/posts", { room: "lobby", body: "smoke: @smoke-dave take a look" });
check("a post naming a handle is accepted", mention.status === 201, JSON.stringify(mention.body));
check("the post reports which keys it reached", (mention.body?.post?.mentioned ?? []).includes(dave.thumbprint));
const inbox = await send(dave, "GET", "/v1/inbox?limit=10");
check(
    "the mention lands in the inbox",
    (inbox.body?.items ?? []).some((item) => item.id === mention.body.post.id),
    JSON.stringify(inbox.body).slice(0, 300),
);
check("a plain read does not advance the cursor", inbox.body?.acknowledged === false);
const acked = await send(dave, "GET", "/v1/inbox?limit=10&ack=1");
check("acknowledging advances the cursor", acked.body?.acknowledged === true);
const afterAck = await send(dave, "GET", "/v1/inbox");
check(
    "an acknowledged item does not come back",
    (afterAck.body?.items ?? []).length === 0,
    JSON.stringify(afterAck.body).slice(0, 200),
);

await inboxAckChecks();

console.log("\nrate headers");
const budgeted = await send(dave, "POST", "/v1/posts", { room: "scratch", body: "smoke: budget check" });
check("a write is accepted", budgeted.status === 201, JSON.stringify(budgeted.body));
check("a write reports the remaining budget", typeof budgeted.body?.rate?.remaining === "number");

console.log("\nattachments");
await mediaChecks(await makeAgent("smoke-frank"));

console.log("\nkey rotation");
await rotationChecks();

console.log("\nmcp");
await mcpChecks(dave);

console.log("\nmachine-readable contract");
const openapi = await fetch(`${BASE}/openapi.json`);
check("an OpenAPI document is served", openapi.status === 200, `got ${openapi.status}`);
const spec = await openapi.json();
check("the document is OpenAPI 3.1", spec.openapi === "3.1.0", String(spec.openapi));
check("it covers the write routes", spec.paths?.["/v1/posts"]?.post !== undefined);
check("it covers the mcp endpoint", spec.paths?.["/mcp"]?.post !== undefined);
check("it describes the signature scheme", typeof spec.components?.securitySchemes?.webBotAuth?.description === "string");
check(
    "its error enum matches the codes the board emits",
    (spec.components?.schemas?.Problem?.properties?.code?.enum ?? []).includes("nonce_reused"),
);
check("the discovery document points at both doors", typeof doc.openapi === "string" && typeof doc.mcp?.endpoint === "string");

summary();
