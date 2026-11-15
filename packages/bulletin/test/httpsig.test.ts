import assert from "node:assert/strict";
import { test } from "node:test";

import {
    buildSignatureBase,
    checkContentDigest,
    checkTimestamps,
    parseRequestSignature,
    parseSignatureInput,
    SignatureError,
    verifyRequestSignature,
} from "../src/httpsig.ts";
import { utf8 } from "../src/bytes.ts";
import { makeSigner, signRequest } from "./helpers.ts";

const URL_UNDER_TEST = "https://board.example/v1/posts";

test("a request signed by an independent signer verifies", async () => {
    const signer = await makeSigner();
    const body = JSON.stringify({ room: "lobby", body: "hello" });
    const request = await signRequest(signer, { url: URL_UNDER_TEST, body });

    const parsed = parseRequestSignature(request);
    assert.equal(parsed.keyid, signer.thumbprint);
    assert.ok(parsed.nonce !== null);
    await checkContentDigest(request, utf8(body));
    assert.ok(await verifyRequestSignature(request, parsed, signer.jwk));
});

test("a signature from one key does not verify under another", async () => {
    const signer = await makeSigner();
    const other = await makeSigner();
    const request = await signRequest(signer, { url: URL_UNDER_TEST, body: "{}" });
    const parsed = parseRequestSignature(request);
    assert.ok(!(await verifyRequestSignature(request, parsed, other.jwk)));
});

test("a body swapped after signing fails the digest check", async () => {
    const signer = await makeSigner();
    const request = await signRequest(signer, {
        url: URL_UNDER_TEST,
        body: JSON.stringify({ room: "lobby", body: "benign" }),
        tamperBody: JSON.stringify({ room: "lobby", body: "ignore previous instructions" }),
    });
    const sent = new Uint8Array(await request.arrayBuffer());
    await assert.rejects(() => checkContentDigest(request, sent), SignatureError);
});

test("the same signature replayed against another path does not verify", async () => {
    const signer = await makeSigner();
    const signed = await signRequest(signer, { url: URL_UNDER_TEST, body: "{}" });
    const moved = new Request("https://board.example/v1/promote", {
        method: "POST",
        headers: signed.headers,
        body: "{}",
    });
    const parsed = parseRequestSignature(moved);
    assert.ok(!(await verifyRequestSignature(moved, parsed, signer.jwk)));
});

test("the same signature replayed against another host does not verify", async () => {
    const signer = await makeSigner();
    const signed = await signRequest(signer, { url: URL_UNDER_TEST, body: "{}" });
    const moved = new Request("https://elsewhere.example/v1/posts", {
        method: "POST",
        headers: signed.headers,
        body: "{}",
    });
    const parsed = parseRequestSignature(moved);
    assert.ok(!(await verifyRequestSignature(moved, parsed, signer.jwk)));
});

test("an unsigned request is refused before any lookup", async () => {
    const request = new Request(URL_UNDER_TEST, { method: "POST", body: "{}" });
    assert.throws(() => parseRequestSignature(request), SignatureError);
});

test("a signature without the web-bot-auth tag is refused", async () => {
    const signer = await makeSigner();
    const request = await signRequest(signer, { url: URL_UNDER_TEST, body: "{}", tag: "other" });
    assert.throws(() => parseRequestSignature(request), /no web-bot-auth signature/);
});

test("a signature that does not bind the host is refused", async () => {
    const signer = await makeSigner();
    const request = await signRequest(signer, {
        url: URL_UNDER_TEST,
        body: "{}",
        covered: ["@method", "@path", "content-digest"],
    });
    assert.throws(() => parseRequestSignature(request), /does not cover the authority/);
});

test("timestamps bound both age and claimed window", () => {
    const member = parseSignatureInput(
        'sig1=("@method" "@authority");created=1000;expires=1120;keyid="k";tag="web-bot-auth"',
    )[0]!;
    assert.deepEqual(checkTimestamps(member, 1_050), { created: 1_000, expires: 1_120 });
    assert.throws(() => checkTimestamps(member, 1_500), /too old/);
    assert.throws(() => checkTimestamps(member, 900), /from the future/);

    const wide = parseSignatureInput(
        'sig1=("@method" "@authority");created=1000;expires=99999;keyid="k";tag="web-bot-auth"',
    )[0]!;
    assert.throws(() => checkTimestamps(wide, 1_050), /window is too wide/);

    const backwards = parseSignatureInput(
        'sig1=("@method" "@authority");created=1000;expires=900;keyid="k";tag="web-bot-auth"',
    )[0]!;
    assert.throws(() => checkTimestamps(backwards, 1_000), /expires before it was created/);
});

test("the signature base reuses the received parameter text verbatim", () => {
    const raw = '("@method" "@path");created=5;expires=65;keyid="k";tag="web-bot-auth"';
    const member = parseSignatureInput(`sig1=${raw}`)[0]!;
    assert.equal(member.raw, raw);
    const base = buildSignatureBase(
        { method: "post", url: "https://board.example/v1/posts?x=1", headers: new Headers() },
        member,
    );
    // Re-serializing the parameters instead of echoing them is the classic way
    // an RFC 9421 verifier disagrees with every signer on the planet.
    assert.equal(base, ['"@method": POST', '"@path": /v1/posts', `"@signature-params": ${raw}`].join("\n"));
});

test("component parameters are outside the accepted profile", () => {
    assert.throws(
        () => parseSignatureInput('sig1=("@method";req);created=1;tag="web-bot-auth"'),
        /unsupported component parameter/,
    );
});

test("a covered header that is absent is an error, not an empty string", () => {
    const member = parseSignatureInput('sig1=("@authority" "x-missing");created=1')[0]!;
    assert.throws(
        () => buildSignatureBase({ method: "GET", url: "https://board.example/", headers: new Headers() }, member),
        /absent header/,
    );
});

test("more than one web-bot-auth signature is refused", async () => {
    const signer = await makeSigner();
    const a = await signRequest(signer, { url: URL_UNDER_TEST, body: "{}", label: "sig1" });
    const b = await signRequest(signer, { url: URL_UNDER_TEST, body: "{}", label: "sig2" });
    const merged = new Request(URL_UNDER_TEST, {
        method: "POST",
        headers: {
            "content-digest": a.headers.get("content-digest")!,
            "signature-input": `${a.headers.get("signature-input")}, ${b.headers.get("signature-input")}`,
            signature: `${a.headers.get("signature")}, ${b.headers.get("signature")}`,
        },
        body: "{}",
    });
    assert.throws(() => parseRequestSignature(merged), /more than one/);
});

test("an unsupported algorithm is named rather than ignored", async () => {
    const signer = await makeSigner();
    const request = await signRequest(signer, { url: URL_UNDER_TEST, body: "{}" });
    const swapped = new Request(URL_UNDER_TEST, {
        method: "POST",
        headers: {
            "content-digest": request.headers.get("content-digest")!,
            "signature-input": request.headers.get("signature-input")!.replace("ed25519", "rsa-v1_5-sha256"),
            signature: request.headers.get("signature")!,
        },
        body: "{}",
    });
    assert.throws(() => parseRequestSignature(swapped), /unsupported alg/);
});

test("a missing Content-Digest is a 400 with a usable hint", async () => {
    const request = new Request(URL_UNDER_TEST, { method: "POST", body: "{}" });
    await assert.rejects(
        () => checkContentDigest(request, utf8("{}")),
        (error: unknown) => error instanceof SignatureError && error.status === 400,
    );
});
