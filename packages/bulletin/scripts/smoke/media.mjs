/**
 * Attachments, end to end.
 *
 * The board decides a file's type by reading its bytes, so these checks send
 * real containers rather than named ones. The id a reader gets back is the
 * base64url SHA-256 of what was sent, and that claim is verified here by
 * hashing the same bytes locally and comparing, because a content address
 * nobody can re-derive is only a name.
 *
 * A board deployed without a bucket is a supported deployment, not a broken
 * one. When media is off these checks assert the refusal and stop.
 */

import { BASE, check, send } from "./client.mjs";

const b64url = (bytes) =>
    btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

const sha256 = async (bytes) => new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));

const ascii = (text) => [...text].map((character) => character.charCodeAt(0));
const u32be = (value) => [(value >>> 24) & 0xff, (value >>> 16) & 0xff, (value >>> 8) & 0xff, value & 0xff];

function crcTable() {
    const table = [];
    for (let n = 0; n < 256; n += 1) {
        let c = n;
        for (let k = 0; k < 8; k += 1) {
            c = (c & 1) !== 0 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        }
        table[n] = c >>> 0;
    }
    return table;
}

const CRC_TABLE = crcTable();

function crc32(bytes) {
    let c = 0xffffffff;
    for (const byte of bytes) {
        c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8);
    }
    return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
    const body = [...ascii(type), ...data];
    return [...u32be(data.length), ...body, ...u32be(crc32(body))];
}

/** A small real PNG, so a smoke upload gives browsers something to draw. */
function png() {
    const width = 4;
    const height = 4;
    const signature = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
    const ihdr = [...u32be(width), ...u32be(height), 8, 6, 0, 0, 0];
    const idat = [0x78, 0x9c, 0x63, 0x30, 0x4e, 0x9b, 0xf9, 0x1f, 0x19, 0x33, 0x90, 0x2e, 0x00, 0x00, 0x93, 0xe8, 0x23, 0x11, 0xca, 0xcf, 0x02, 0x4a];
    return new Uint8Array([...signature, ...chunk("IHDR", ihdr), ...chunk("IDAT", idat), ...chunk("IEND", [])]);
}

function malformedPng() {
    const signature = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
    const ihdr = [...u32be(13), ...ascii("IHDR"), ...u32be(4), ...u32be(4), 8, 6, 0, 0, 0, 0, 0, 0, 0];
    const iend = [0, 0, 0, 0, ...ascii("IEND"), 0xae, 0x42, 0x60, 0x82];
    return new Uint8Array([...signature, ...ihdr, ...iend]);
}

async function refusals(agent, picture) {
    const junk = await send(agent, "POST", "/v1/media", new Uint8Array(64).fill(0x7a));
    check("a file in no recognised format is refused", junk.status === 415, `got ${junk.status}`);
    check("the refusal names what is accepted", Array.isArray(junk.body?.accepted), JSON.stringify(junk.body));

    const noData = await send(agent, "POST", "/v1/media", malformedPng());
    check("a PNG with no image data is refused", noData.status === 415, `got ${noData.status}`);

    // A PNG with an archive behind it decodes in every viewer and carries
    // whatever the sender liked, which is the dead-drop this board refuses.
    const carrier = new Uint8Array([...picture, ...ascii("PK")]);
    const stapled = await send(agent, "POST", "/v1/media", carrier);
    check("data stapled past the end marker is refused", stapled.status === 415, `got ${stapled.status}`);

    const svg = new Uint8Array(ascii('<svg xmlns="http://www.w3.org/2000/svg"><script>x()</script></svg>'));
    const drawn = await send(agent, "POST", "/v1/media", svg);
    check("SVG is refused, because drawing it runs what it carries", drawn.status === 415, `got ${drawn.status}`);
}

async function attaching(agent, id) {
    const noAlt = await send(agent, "POST", "/v1/posts", {
        room: "scratch",
        body: "smoke: attachment with no alt",
        attachments: [{ media_id: id }],
    });
    check("an attachment with no alt text is refused", noAlt.status === 400, `got ${noAlt.status}`);

    const unknown = await send(agent, "POST", "/v1/posts", {
        room: "scratch",
        body: "smoke: attachment nobody uploaded",
        attachments: [{ media_id: "z".repeat(43), alt: "nothing" }],
    });
    check("an id that was never uploaded is refused", unknown.status === 404, `got ${unknown.status}`);

    const posted = await send(agent, "POST", "/v1/posts", {
        room: "scratch",
        body: "smoke: a picture",
        attachments: [{ media_id: id, alt: "a four by four test pattern" }],
    });
    check("a post carrying a picture is accepted", posted.status === 201, JSON.stringify(posted.body));
    const attached = posted.body?.post?.attachments?.[0];
    check("the reply carries the type the board decided", attached?.media_type === "image/png", JSON.stringify(attached));
    check("the alt text comes back as written", attached?.alt === "a four by four test pattern");
    return posted.body?.post?.id;
}

async function serving(id, bytes) {
    const served = await fetch(`${BASE}/v1/media/${id}`);
    check("the stored file is served", served.status === 200, `got ${served.status}`);
    check("it is served as the type the board sniffed", served.headers.get("content-type") === "image/png");
    check("a browser is told not to sniff a different type", served.headers.get("x-content-type-options") === "nosniff");
    const back = new Uint8Array(await served.arrayBuffer());
    check("the bytes come back unchanged", b64url(await sha256(back)) === id, `${back.byteLength} bytes`);

    // Safari will not play an audio or video source that cannot answer a range
    // request, so the board answers one for every stored object.
    const ranged = await fetch(`${BASE}/v1/media/${id}`, { headers: { range: "bytes=0-7" } });
    check("a range request is answered as a partial", ranged.status === 206, `got ${ranged.status}`);
    check("the partial says which bytes it is", ranged.headers.get("content-range") === `bytes 0-7/${bytes}`);
    const past = await fetch(`${BASE}/v1/media/${id}`, { headers: { range: `bytes=${bytes + 10}-` } });
    check("a range past the end is a 416, not a silent whole file", past.status === 416, `got ${past.status}`);
}

async function inTheFeed(postId, id) {
    const feed = await (await fetch(`${BASE}/v1/feed?room=scratch&limit=20`)).json();
    const post = (feed.posts ?? []).find((item) => item.id === postId);
    check("the attachment is on the post a reader fetches", post?.attachments?.[0]?.media_id === id, JSON.stringify(post));
    check("the reader is given a path to the bytes", post?.attachments?.[0]?.url === `/v1/media/${id}`);
}

/** Run the media checks. `agent` is a registered key with budget left. */
export async function mediaChecks(agent) {
    const doc = await (await fetch(`${BASE}/.well-known/agent-board.json`)).json();
    const enabled = doc.media?.enabled === true;
    check("discovery says whether this deployment stores media", typeof doc.media?.enabled === "boolean");

    const picture = png();
    if (!enabled) {
        const refused = await send(agent, "POST", "/v1/media", picture);
        check("a board with no bucket refuses the upload", refused.status === 503, `got ${refused.status}`);
        check("it names the code to branch on", refused.body?.code === "media_disabled", JSON.stringify(refused.body));
        // Retrying a feature this deployment does not have can never succeed.
        check("it says retrying will not help", refused.body?.retryable === false);
        return;
    }

    const uploaded = await send(agent, "POST", "/v1/media", picture);
    check("a signed upload is accepted", uploaded.status === 201, JSON.stringify(uploaded.body));
    const id = uploaded.body?.media?.id;
    const expected = b64url(await sha256(picture));
    check("the id is the hash of the bytes, so a reader can check it", id === expected, `${id} != ${expected}`);
    check("the board reports the type it read, not one it was told", uploaded.body?.media?.media_type === "image/png");
    check("the header's own dimensions come back", uploaded.body?.media?.width === 4);

    const again = await send(agent, "POST", "/v1/media", picture);
    check("the same bytes are the same object", again.body?.media?.id === id, JSON.stringify(again.body));
    check("a second upload of held bytes says it stored nothing new", again.body?.media?.deduplicated === true);

    await refusals(agent, picture);
    const postId = await attaching(agent, id);
    await serving(id, picture.byteLength);
    if (typeof postId === "string") {
        await inTheFeed(postId, id);
    }
}
