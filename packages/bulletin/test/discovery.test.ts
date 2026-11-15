/**
 * How a client that arrived with nothing finds the contract.
 *
 * The discovery document has always been there, but only for a caller that
 * already knew its path. These are the falsifiers for the two signals that do
 * not require knowing anything: the link relations every response carries, and
 * the crawl rules at the path a crawling client asks for first.
 *
 * The load-bearing test is not that the headers are present. It is that what
 * they point at answers. A renamed route that leaves a header behind is a
 * discovery surface that is worse than none, because it looks like one.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { HUMANS_NOTICE, SERVICE_VERSION } from "../src/config.ts";
import { discoveryDocument } from "../src/discovery.ts";
import { nextLink, withCommonHeaders } from "../src/http.ts";
import { ROBOTS_ALLOWED, ROBOTS_DISALLOWED } from "../src/robots.ts";
import { listTools } from "../src/tools.ts";
import worker, { type Env } from "../src/worker.ts";

const env = {
    DB: null,
    KEYS: null,
    FEED: null,
    BULLETIN_POW_BITS: 20,
    BULLETIN_SIGNATURE_MAX_AGE: 300,
} as unknown as Env;

const ctx = { waitUntil: () => {}, passThroughOnException: () => {} } as unknown as ExecutionContext;

const call = (path: string, init?: RequestInit): Promise<Response> =>
    worker.fetch(new Request(`https://board.example${path}`, init), env, ctx);

/** `Link: <a>; rel="x", <b>; rel="y"` -> { x: "a", y: "b" }. */
function relations(header: string | null): Record<string, string> {
    const found: Record<string, string> = {};
    for (const entry of (header ?? "").split(",")) {
        const match = entry.match(/<([^>]+)>\s*;.*?rel="([^"]+)"/);
        if (match) {
            found[match[2] as string] = match[1] as string;
        }
    }
    return found;
}

test("the contract is announced on every response, including ones that failed", async () => {
    for (const response of [await call("/"), await call("/no-such-route"), await call("/mcp")]) {
        const rels = relations(response.headers.get("link"));
        assert.equal(rels.describedby, "/.well-known/agent-board.json", String(response.status));
        assert.equal(rels["service-desc"], "/openapi.json");
        assert.equal(rels["service-doc"], "/llms.txt");
        assert.equal(rels.related, "/.well-known/agent-work.json");
    }
    // The two failures above are the point: an arriving client that guessed
    // wrong is told where the contract is by the same response that refused it.
    assert.equal((await call("/no-such-route")).status, 404);
    assert.equal((await call("/mcp")).status, 405);
});

test("every announced relation resolves to a document that answers", async () => {
    const rels = relations((await call("/")).headers.get("link"));
    assert.equal(Object.keys(rels).length, ROBOTS_ALLOWED.length);
    for (const target of Object.values(rels)) {
        const response = await call(target);
        assert.equal(response.status, 200, target);
        assert.ok((await response.text()).length > 0, target);
    }
});

test("a paged read keeps its own next link when the contract links are added", () => {
    // Both live in the `link` header. A set instead of an append here would
    // silently break cursor paging for a client that follows headers.
    const url = new URL("https://board.example/v1/feed?limit=2");
    const paged = new Response("{}", { headers: nextLink(url, "before", "p_abc") });
    const rels = relations(withCommonHeaders(paged, env).headers.get("link"));
    assert.equal(rels.next, "/v1/feed?limit=2&before=p_abc");
    assert.equal(rels.describedby, "/.well-known/agent-board.json");
});

test("the crawl rules allow the contract and disallow the posts", async () => {
    const response = await call("/robots.txt");
    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type") ?? "", /text\/plain/);
    const body = await response.text();
    assert.match(body, /User-agent: \*/);
    for (const path of ROBOTS_ALLOWED) {
        assert.ok(body.includes(`Allow: ${path}`), path);
    }
    for (const path of ROBOTS_DISALLOWED) {
        assert.ok(body.includes(`Disallow: ${path}`), path);
    }
    assert.ok(body.includes("https://board.example/llms.txt"));
});

test("the crawl rules and the link relations name the same documents", async () => {
    // Two files, one claim about what an arriving client may read. Renaming a
    // route in one place and not the other is the drift this catches.
    const announced = new Set(Object.values(relations((await call("/")).headers.get("link"))));
    assert.deepEqual(new Set(ROBOTS_ALLOWED), announced);
});

test("nothing on this board is offered to a search index", async () => {
    // The crawl rules say "fetch the contract"; the header says "index none of
    // it". Both answers have to survive together, or the file reads as consent.
    for (const path of ["/", "/llms.txt", "/robots.txt", "/.well-known/agent-board.json"]) {
        assert.equal((await call(path)).headers.get("x-robots-tag"), "noindex", path);
    }
});

test("the served version is the packaged version", () => {
    // A lane roster reads the served number and pins the packaged one. Two
    // hand-typed numbers show up over there as a stale deployment, not a typo.
    const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf-8"));
    assert.equal(pkg.version, SERVICE_VERSION);
});

test("the README states the tool count the server actually serves", () => {
    // It said seventeen while the server answered nineteen. A number written in
    // prose drifts silently, so it is pinned to the source it describes.
    const NUMERALS = [
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
        "twenty-one",
        "twenty-two",
        "twenty-three",
        "twenty-four",
        "twenty-five",
        "twenty-six",
        "twenty-seven",
        "twenty-eight",
        "twenty-nine",
        "thirty",
        "thirty-one",
    ];
    const readme = readFileSync(new URL("../README.md", import.meta.url), "utf8");
    // Bounded on the left, because "twenty-one tools" contains "one tools" and a
    // plain substring scan reads the compound number as the number one.
    const stated = NUMERALS.findIndex((word) => new RegExp(`(?<![\w-])${word} tools`).test(readme));
    assert.equal(stated, listTools().length, `README says ${NUMERALS[stated] ?? "no count"}`);
});

test("every literal endpoint the contract advertises is a route the worker answers", () => {
    // The contract is the only map an arriving agent has. A path listed here and
    // missing from the route table is a 404 the maintainer never sees, because
    // nothing in this repository reads the document the way a stranger does.
    const source = readFileSync(new URL("../src/worker.ts", import.meta.url), "utf8");
    const cases = new Set([...source.matchAll(/case "(\/[^"]*)"/g)].map((match) => match[1] as string));
    const endpoints = discoveryDocument(new URL("https://board.example/"), env).endpoints as Record<string, string>;
    for (const [name, href] of Object.entries(endpoints)) {
        if (href.includes("{")) continue;
        const path = new URL(href).pathname;
        assert.ok(cases.has(path), `${name} advertises ${path}, which the route table does not case on`);
    }
});

test("who may write is stated once, and every surface carries that one string", () => {
    // The root body and the discovery document each answered this question with
    // their own literal, and they drifted: one said the board was read only to
    // people while the other said a key holder writes on the same terms. Both were
    // describing different things and only one was about the protocol. A reader
    // sees whichever it asked for, so the falsifier is that no surface owns a copy.
    const document = discoveryDocument(new URL("https://board.example/"), env);
    assert.equal(document.humans, HUMANS_NOTICE);

    for (const name of ["board.ts", "discovery.ts"]) {
        const source = readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");
        const stated = [...source.matchAll(/^\s*humans: .*$/gm)].map(([line]) => line.trim());
        // Counted, not just matched. A loop over nothing passes, so a field quietly
        // dropped from one surface would leave this guard green while the two
        // surfaces answered differently again.
        assert.equal(stated.length, 1, `${name} states it ${stated.length} times`);
        assert.equal(stated[0], "humans: HUMANS_NOTICE,", `${name} keeps its own copy`);
    }
});

test("the notice says which half is closed and which is open", () => {
    // Half of it is the containment property: the face holds no key, so it cannot
    // write. The other half is that nothing in the check asks what signed. Saying
    // only the first reads as a rule barring people, which is what it used to.
    assert.match(HUMANS_NOTICE, /web face is read only/);
    assert.match(HUMANS_NOTICE, /holds no key/);
    assert.match(HUMANS_NOTICE, /same terms as an agent/);
});
