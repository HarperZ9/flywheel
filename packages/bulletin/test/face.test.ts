/**
 * The face, checked against the two things it claims about itself.
 *
 * The first claim is the no-markup rule. CI already greps `public/js/` for
 * three assignment sinks, which catches the ones it names and runs nowhere
 * else. This adds `eval` and `new Function`, runs in `npm test` where the
 * change is made, and carries the control that grep cannot: a source that does
 * assign innerHTML, which the scanner must flag. A scan for a bare word would
 * be satisfied by the comments in `render.js` and `media.js` that say there is
 * no innerHTML in the file, so comments come out before the scan looks. If the
 * control stops failing, the scanner has gone blind and the rest is worthless.
 *
 * The second claim is that the JSON API is the durable interface and needs no
 * browser. That was true of the board and false of this page: the feed is drawn
 * from script and the two join links are filled from script, so a reader with
 * scripting off got an empty list under a live header and two anchors pointing
 * at `#`. The noscript block carries absolute links now. They have to point at
 * the origin the page is configured for, and they have to name routes the board
 * serves, or the fallback is worse than none.
 *
 * Nothing here reaches the network. The route list comes from the same module
 * the worker answers `/openapi.json` from.
 */

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";

import { openApiDocument } from "../src/openapi.ts";
import type { Env } from "../src/config.ts";

const ROOT = new URL("../", import.meta.url);
const FACE = readFileSync(new URL("public/index.html", ROOT), "utf8");

const ENV = { BULLETIN_POW_BITS: 20, BULLETIN_SIGNATURE_MAX_AGE: 300 } as unknown as Env;

/** Ways to hand a string to the HTML parser. None of them belongs in the face. */
const SINKS: Array<[string, RegExp]> = [
    ["innerHTML", /\.innerHTML\s*=/],
    ["outerHTML", /\.outerHTML\s*=/],
    ["insertAdjacentHTML", /insertAdjacentHTML\s*\(/],
    ["document.write", /document\s*\.\s*write(?:ln)?\s*\(/],
    ["eval", /(?:^|[^.\w])eval\s*\(/],
    ["new Function", /new\s+Function\s*\(/],
];

/**
 * Comments out, so a file that only talks about innerHTML reads as clean.
 *
 * A line comment is `//` that is not the `//` in a URL, which is why the scheme
 * colon is excluded rather than the whole sequence matched.
 */
function stripComments(source: string): string {
    return source.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

function sinksIn(source: string): string[] {
    const code = stripComments(source);
    return SINKS.filter(([, pattern]) => pattern.test(code)).map(([name]) => name);
}

function faceScripts(): Array<[string, string]> {
    const dir = new URL("public/js/", ROOT);
    return readdirSync(dir)
        .filter((name) => name.endsWith(".js"))
        .map((name) => [name, readFileSync(new URL(name, dir), "utf8")]);
}

/** Every capture of `pattern` in `source`, skipping any group that did not match. */
function captures(source: string, pattern: RegExp, group = 1): string[] {
    const found: string[] = [];
    for (const match of source.matchAll(pattern)) {
        const value = match[group];
        if (value !== undefined) found.push(value);
    }
    return found;
}

/** The href of every anchor inside the noscript block, in document order. */
function noscriptLinks(): string[] {
    const block = FACE.match(/<noscript>([\s\S]*?)<\/noscript>/)?.[1];
    assert.ok(block, "the face has no noscript block");
    return captures(block, /href="([^"]+)"/g);
}

/** The board origin the page is configured for, without a trailing slash. */
function boardOrigin(): string {
    const configured = FACE.match(/data-board="([^"]*)"/)?.[1];
    assert.ok(configured, "the html element carries no data-board");
    return configured.replace(/\/$/, "");
}

test("no script in the face hands a string to the HTML parser", () => {
    const scripts = faceScripts();
    assert.ok(scripts.length >= 4, "expected the face's four modules, found " + scripts.length);
    for (const [name, source] of scripts) {
        assert.deepEqual(sinksIn(source), [], `${name} reaches an HTML sink`);
    }
});

test("the scanner is not satisfied by a comment saying there is no innerHTML", () => {
    const honest = "/* there is no innerHTML in this file and there should never be one. */";
    assert.deepEqual(sinksIn(honest), [], "a comment about innerHTML must not count as one");
    const lying = honest + "\nnode.innerHTML = post.body;\n";
    assert.deepEqual(sinksIn(lying), ["innerHTML"], "the scanner missed a real assignment");
    assert.deepEqual(sinksIn("el.insertAdjacentHTML('beforeend', body);"), ["insertAdjacentHTML"]);
    assert.deepEqual(sinksIn("const url = 'https://board.example/v1/feed';"), [],
        "a URL is not a line comment");
});

test("the page carries no inline script of its own", () => {
    const inline = captures(FACE, /<script\b[^>]*>([\s\S]*?)<\/script>/g)
        .filter((body) => body.trim().length > 0);
    assert.deepEqual(inline, [], "the face's behaviour belongs in public/js/");
    const external = captures(FACE, /<script\b[^>]*\bsrc="([^"]+)"/g);
    assert.deepEqual(external, ["js/app.js"], "the face loads one module and no other");
});

test("the noscript links point at the board the page is configured for", () => {
    const origin = boardOrigin();
    assert.ok(origin.length > 0, "data-board is empty, so the fallback links cannot resolve");
    const links = noscriptLinks();
    assert.ok(links.length >= 3, "expected the feed, the rooms, and discovery");
    for (const href of links) {
        assert.ok(href.startsWith(origin + "/"),
            `${href} does not point at the configured board ${origin}`);
    }
});

test("every route the noscript names is a route the board serves", () => {
    const doc = openApiDocument(new URL("https://board.example/"), ENV) as {
        paths?: Record<string, unknown>;
    };
    assert.ok(doc.paths, "openApiDocument stopped reporting paths, so this test proves nothing");
    const paths = Object.keys(doc.paths);
    const origin = boardOrigin();
    for (const href of noscriptLinks()) {
        const path = href.slice(origin.length);
        assert.ok(paths.includes(path), `the fallback offers ${path}, which the board does not serve`);
    }
});

test("the links the page fills from script are the ones it leaves empty", () => {
    const placeholders = [...FACE.matchAll(/<a id="(link-[a-z]+)" href="([^"]*)"/g)];
    assert.ok(placeholders.length > 0, "the join section has no script-filled links");
    for (const [, id, href] of placeholders) {
        assert.equal(href, "#", `${id} carries a hard-coded href that script then overwrites`);
    }
    const app = readFileSync(new URL("public/js/app.js", ROOT), "utf8");
    for (const [, id] of placeholders) {
        assert.ok(app.includes(`getElementById("${id}")`), `nothing fills ${id}`);
    }
});
