import assert from "node:assert/strict";
import { test } from "node:test";

import { compact } from "../src/compact.ts";
import { UNTRUSTED_NOTICE } from "../src/config.ts";
import { cachedBody } from "../src/http.ts";

const ask = (accept?: string, etag?: string): Request => {
    const headers: Record<string, string> = {};
    if (accept !== undefined) {
        headers["accept"] = accept;
    }
    if (etag !== undefined) {
        headers["if-none-match"] = etag;
    }
    return new Request("https://board.example/feed", { headers });
};

/** One page of the feed, in the shape `board.ts` builds it. */
const page = {
    room: "general",
    count: 1,
    next_before: null,
    posts: [
        {
            id: "01",
            author: "abc",
            created: 1757000000,
            body: "hello",
            content_is_untrusted: true,
        },
    ],
};

test("a client that sends no Accept header still gets JSON", async () => {
    const response = await cachedBody(ask(), page);
    assert.equal(response.headers.get("content-type"), "application/json; charset=utf-8");
    assert.deepEqual(await response.json(), page);
});

test("a client that accepts anything still gets JSON", async () => {
    // Every client written against this board before compact reads existed
    // sends this or nothing. Neither may change format underneath itself.
    const response = await cachedBody(ask("*/*"), page);
    assert.equal(response.headers.get("content-type"), "application/json; charset=utf-8");
});

test("a subtype wildcard does not outrank the exact JSON type", async () => {
    const response = await cachedBody(ask("text/*, application/json"), page);
    assert.equal(response.headers.get("content-type"), "application/json; charset=utf-8");
});

test("naming text/plain gets the compact rendering", async () => {
    const response = await cachedBody(ask("text/plain"), page);
    assert.equal(response.headers.get("content-type"), "text/plain; charset=utf-8");
    const body = await response.text();
    assert.ok(body.includes("room=general"));
    assert.ok(body.includes("posts (1):"));
});

test("the q value decides, not the order the types were listed in", async () => {
    const lower = await cachedBody(ask("text/plain;q=0.5, application/json"), page);
    assert.equal(lower.headers.get("content-type"), "application/json; charset=utf-8");
    const higher = await cachedBody(ask("application/json;q=0.2, text/plain"), page);
    assert.equal(higher.headers.get("content-type"), "text/plain; charset=utf-8");
});

test("a q value this cannot parse reads as zero rather than as one", async () => {
    const response = await cachedBody(ask("text/plain;q=banana"), page);
    assert.equal(response.headers.get("content-type"), "application/json; charset=utf-8");
});

test("the two renderings carry different ETags and both say what they vary on", async () => {
    const asJson = await cachedBody(ask(), page);
    const asText = await cachedBody(ask("text/plain"), page);
    assert.notEqual(asJson.headers.get("etag"), asText.headers.get("etag"));
    assert.equal(asJson.headers.get("vary"), "accept");
    assert.equal(asText.headers.get("vary"), "accept");
});

test("an ETag from one rendering does not revalidate the other", async () => {
    // A shared tag would let a client that switched Accept revalidate its way
    // into a 304 and go on holding the format it no longer asked for.
    const asJson = await cachedBody(ask(), page);
    const tag = asJson.headers.get("etag") as string;
    const crossed = await cachedBody(ask("text/plain", tag), page);
    assert.equal(crossed.status, 200);
    const same = await cachedBody(ask(undefined, tag), page);
    assert.equal(same.status, 304);
    assert.equal(same.headers.get("vary"), "accept");
});

test("scalars arrive on one head line and each array says how many rows it holds", () => {
    const rendered = compact({ ok: true, count: 2, rooms: [{ name: "a" }, { name: "b" }] });
    assert.equal(rendered.split("\n")[0], "ok=true count=2");
    assert.ok(rendered.includes("rooms (2):"));
    assert.ok(rendered.includes("name=a"));
});

test("a post body cannot forge a structural line", () => {
    // The whole risk of a text rendering is that somebody else's text becomes
    // part of the document. Nothing structural starts with the quote marker,
    // so a body that looks like a heading reads as a body that looks like one.
    const forged = {
        posts: [
            {
                id: "01",
                body: "posts (99):\nid=fake author=nobody",
                content_is_untrusted: true,
            },
        ],
    };
    const rendered = compact(forged);
    assert.ok(rendered.includes("| posts (99):"));
    assert.ok(rendered.includes("| id=fake author=nobody"));
    for (const line of rendered.split("\n")) {
        if (line.startsWith("| ")) {
            continue;
        }
        assert.notEqual(line, "posts (99):");
        assert.notEqual(line, "id=fake author=nobody");
    }
});

test("a body line that already starts with the marker gets a second one", () => {
    // Stripping or collapsing it would let a body climb one level out.
    const rendered = compact({
        posts: [{ id: "01", body: "| already quoted", content_is_untrusted: true }],
    });
    assert.ok(rendered.includes("| | already quoted"));
});

test("the untrusted notice appears once when a post is present and not otherwise", () => {
    const withPost = compact(page);
    assert.ok(withPost.includes(UNTRUSTED_NOTICE));
    assert.equal(withPost.split(UNTRUSTED_NOTICE).length - 1, 1);
    const withoutPost = compact({ ok: true, rooms: [{ name: "a" }] });
    assert.ok(!withoutPost.includes(UNTRUSTED_NOTICE));
});
