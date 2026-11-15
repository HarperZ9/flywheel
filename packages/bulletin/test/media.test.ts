import assert from "node:assert/strict";
import { test } from "node:test";

import { decodeBase64Loose, encodeBase64Url, sha256 } from "../src/bytes.ts";
import { hashInput, publicAttachment, resolveAttachments, type Attachment } from "../src/media/attach.ts";
import { ACCEPTED_TYPES, sniff } from "../src/media/sniff.ts";
import { indexAttachments } from "../src/views.ts";
import { TIER_POLICY } from "../src/tiers.ts";
import worker, { type Env } from "../src/worker.ts";
import { ascii, png } from "./media-fixtures.ts";

/**
 * Attachments are the one place this board takes bytes it did not generate and
 * hands them back to a browser. What is tested here is the part that decides
 * whether to take them at all: the sniff, the alt text, and the content hash
 * that binds an attachment to the body its author signed.
 *
 * The steganography null is not tested because it cannot be. A payload hidden
 * inside a valid image passes every check in this file, and the board says so
 * in `does_not_claim` rather than pretending otherwise.
 */

/* --------------------------------------------------------------- fixtures */

function u32le(value: number): number[] {
    return [value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff];
}

function gif(width: number, height: number): Uint8Array {
    const header = [...ascii("GIF89a"), width & 0xff, width >>> 8, height & 0xff, height >>> 8, 0, 0, 0];
    return new Uint8Array([...header, ...new Array(31 - header.length).fill(0), 0x3b]);
}

function wav(): Uint8Array {
    const body = [...ascii("WAVE"), ...ascii("fmt "), ...new Array(24).fill(0)];
    return new Uint8Array([...ascii("RIFF"), ...u32le(body.length), ...body]);
}

/* ------------------------------------------------------------------ sniff */

test("the type is read out of the bytes, not out of a label", () => {
    assert.equal(sniff(png(64, 48)).type, "image/png");
    assert.equal(sniff(gif(12, 9)).type, "image/gif");
    assert.equal(sniff(wav()).type, "audio/wav");
});

test("the header's own dimensions come back with the type", () => {
    const format = sniff(png(1920, 1080));
    assert.equal(format.width, 1920);
    assert.equal(format.height, 1080);
    assert.equal(format.kind, "image");
});

test("SVG is refused, because a browser drawing it runs whatever it carries", () => {
    const svg = new Uint8Array(ascii('<svg xmlns="http://www.w3.org/2000/svg"><script>x()</script></svg>'));
    assert.throws(
        () => sniff(svg),
        (error: any) => {
            assert.equal(error.status, 415);
            assert.equal(error.code, "media_unsupported");
            return true;
        },
    );
    assert.ok(!ACCEPTED_TYPES.includes("image/svg+xml"));
});

test("data stapled to the end of a picture is a refusal, not a passenger", () => {
    // A PNG with an archive behind it decodes fine everywhere and carries
    // whatever the sender liked. Checking the container's own end marker is
    // what makes that a rejection.
    const carrier = new Uint8Array([...png(4, 4), ...ascii("PK")]);
    assert.throws(() => sniff(carrier), /does not end at its IEND/);
});

test("a container whose declared size disagrees with the bytes sent is refused", () => {
    const lying = wav();
    lying[4] = 0xff;
    assert.throws(() => sniff(lying), /size does not match/);
});

test("bytes too short to hold a header are refused rather than guessed at", () => {
    assert.throws(() => sniff(new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])), /too short/);
});

test("an unrecognised format names what the board does accept", () => {
    const noise = new Uint8Array(64).fill(0x7a);
    assert.throws(
        () => sniff(noise),
        (error: any) => {
            assert.equal(error.code, "media_unsupported");
            assert.deepEqual(error.extra.accepted, ACCEPTED_TYPES);
            return true;
        },
    );
});

/* --------------------------------------------------------------- the hash */

const ATTACHMENT: Attachment = {
    mediaId: "a".repeat(43),
    alt: "a screenshot of the failing test",
    mediaType: "image/png",
    kind: "image",
    bytes: 512,
    width: 64,
    height: 48,
};

test("a post with no attachments hashes exactly as it did before attachments existed", async () => {
    // Every content hash already published stays correct, or the board broke a
    // promise to the readers who wrote the old ones down.
    const body = "the parser drops the last row when the file has no trailing newline";
    assert.equal(hashInput(body, []), body);
    const before = encodeBase64Url(await sha256(new TextEncoder().encode(body)));
    const after = encodeBase64Url(await sha256(new TextEncoder().encode(hashInput(body, []))));
    assert.equal(after, before);
});

test("the hash covers the alt text, so nobody can relabel someone else's picture", () => {
    const honest = hashInput("look", [ATTACHMENT]);
    const relabelled = hashInput("look", [{ ...ATTACHMENT, alt: "an unrelated chart" }]);
    assert.notEqual(honest, relabelled);
    assert.match(honest, /bulletin-media:v1:/);
});

test("the hash covers which file is attached", () => {
    const swapped = hashInput("look", [{ ...ATTACHMENT, mediaId: "b".repeat(43) }]);
    assert.notEqual(hashInput("look", [ATTACHMENT]), swapped);
});

/* ---------------------------------------------------------- alt and shape */

const MEDIA_ROW = {
    id: ATTACHMENT.mediaId,
    media_type: "image/png",
    kind: "image",
    bytes: 512,
    width: 64,
    height: 48,
    first_uploader: "someone",
    created_at: 1,
    withheld: 0,
};

/** A D1 stand-in holding media rows, which is all resolveAttachments reads. */
function envWith(rows: Record<string, unknown>[]): Env {
    const db = {
        prepare: () => ({
            bind: (id: string) => ({
                first: async () => rows.find((row) => row.id === id) ?? null,
            }),
        }),
    };
    return { DB: db } as unknown as Env;
}

const env = envWith([MEDIA_ROW]);
const limit = TIER_POLICY.probation.maxAttachments;

function refused(raw: unknown, pattern: RegExp): Promise<void> {
    return assert.rejects(() => resolveAttachments(env, raw, limit), pattern);
}

test("an attachment with no alt text is refused", async () => {
    await refused([{ media_id: ATTACHMENT.mediaId }], /needs alt text/);
    await refused([{ media_id: ATTACHMENT.mediaId, alt: "   " }], /alt text is empty/);
});

test("alt text is capped, because it is prose and not a place to park a payload", async () => {
    await refused([{ media_id: ATTACHMENT.mediaId, alt: "x".repeat(500) }], /too long/);
});

test("an id that was never uploaded is refused before the post is written", async () => {
    await refused([{ media_id: "z".repeat(43), alt: "anything" }], /no such media/);
    await refused([{ media_id: "not-an-id", alt: "anything" }], /not a media id/);
});

test("a withheld object cannot be re-attached to a new post", async () => {
    const withheld = envWith([{ ...MEDIA_ROW, withheld: 1 }]);
    await assert.rejects(
        () => resolveAttachments(withheld, [{ media_id: ATTACHMENT.mediaId, alt: "again" }], limit),
        /withheld/,
    );
});

test("the tier's attachment count is enforced and says what the limit was", async () => {
    const many = new Array(limit + 1).fill({ media_id: ATTACHMENT.mediaId, alt: "one of many" });
    await assert.rejects(
        () => resolveAttachments(env, many, limit),
        (error: any) => {
            assert.equal(error.extra.limit, limit);
            return true;
        },
    );
});

test("the same file twice in one post is a mistake worth naming", async () => {
    const twice = [
        { media_id: ATTACHMENT.mediaId, alt: "first" },
        { media_id: ATTACHMENT.mediaId, alt: "second" },
    ];
    await refused(twice, /attached twice/);
});

test("no attachments field at all is a post with no attachments", async () => {
    assert.deepEqual(await resolveAttachments(env, undefined, limit), []);
    assert.deepEqual(await resolveAttachments(env, null, limit), []);
    await refused("one.png", /must be an array/);
});

test("what a reader sees carries the type the board decided, not the one sent", async () => {
    const resolved = await resolveAttachments(env, [{ media_id: ATTACHMENT.mediaId, alt: "a chart" }], limit);
    assert.equal(resolved.length, 1);
    const view = publicAttachment(resolved[0]!);
    assert.equal(view.media_type, "image/png");
    assert.equal(view.alt, "a chart");
    assert.equal(view.url, `/v1/media/${ATTACHMENT.mediaId}`);
});

/* ------------------------------------------------------------ withholding */

test("a withheld attachment stays visible as a marker with no way to fetch it", () => {
    const index = indexAttachments([
        {
            post_id: "p1",
            media_id: ATTACHMENT.mediaId,
            ordinal: 0,
            alt: "what it was",
            media_type: "image/png",
            kind: "image",
            bytes: 512,
            width: 64,
            height: 48,
            withheld: 1,
        },
    ]);
    const views = index.get("p1") ?? [];
    assert.equal(views.length, 1);
    const view = views[0]!;
    // Dropping the row would leave a reader unable to re-derive the post's
    // content hash and unable to see why it no longer matches.
    assert.equal(view.withheld, true);
    assert.equal(view.url, null);
    assert.equal(view.alt, "what it was");
    assert.equal(view.media_type, undefined);
});

/* ------------------------------------------------------------------ base64 */

test("an upload sent as base64 is read in either spelling", () => {
    const bytes = [0xfb, 0xff, 0xbf, 0x00];
    assert.deepEqual([...decodeBase64Loose("+/+/AA==")], bytes);
    assert.deepEqual([...decodeBase64Loose("-_-_AA")], bytes);
});

/* -------------------------------------------------- a board with no bucket */

test("a board deployed without a bucket says so instead of failing like a bug", async () => {
    const bare = { DB: null, KEYS: null, FEED: null } as unknown as Env;
    const ctx = { waitUntil: () => {}, passThroughOnException: () => {} } as unknown as ExecutionContext;
    const response = await worker.fetch(
        new Request(`https://board.example/v1/media/${ATTACHMENT.mediaId}`),
        bare,
        ctx,
    );
    assert.equal(response.status, 503);
    const problem = (await response.json()) as Record<string, any>;
    assert.equal(problem.code, "media_disabled");
    // Retrying a feature this deployment does not have can never succeed.
    assert.equal(problem.retryable, false);
});
