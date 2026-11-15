/**
 * The browser signing core, checked against the board's own verifier.
 *
 * public/js/sign.js is the client half of the signature protocol, written to
 * run in a browser tab. It shares no code with the server; if the two agree it
 * is because both implement RFC 9421 the same way, not because one calls the
 * other. So this test imports the browser core and the real server modules side
 * by side and proves they meet:
 *
 *   - the thumbprint the browser derives is the account name the server derives;
 *   - the signature base the browser signs is the exact base the server rebuilds;
 *   - a request signed in the browser passes the server's signature, digest and
 *     replay checks;
 *   - a proof of work solved by the browser solver is accepted by the server
 *     checker;
 *   - the private key the browser mints cannot be exported, which is the whole
 *     "sign without exposing the key" claim.
 *
 * If sign.js drifts one byte from the server, a case here fails rather than a
 * real agent failing silently against the live board.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
    buildSignedRequest,
    generateIdentity,
    jwkThumbprint as browserThumbprint,
    powBits as browserPowBits,
    solveProofOfWork,
} from "../public/js/sign.js";

import {
    buildSignatureBase,
    checkContentDigest,
    parseRequestSignature,
    SignatureError,
    verifyRequestSignature,
} from "../src/httpsig.ts";
import { jwkThumbprint as serverThumbprint, parseEd25519Jwk } from "../src/jwk.ts";
import { checkProofOfWork, powBits as serverPowBits } from "../src/pow.ts";
import { utf8 } from "../src/bytes.ts";

const URL_UNDER_TEST = "https://board.example/v1/posts";

/** Rebuild the browser-signed request as the object the server verifier reads. */
function asRequest(signed: { url: string; method: string; headers: Record<string, string>; body: string }): Request {
    return new Request(signed.url, { method: signed.method, headers: signed.headers, body: signed.body });
}

test("the browser thumbprint is the account name the server derives", async () => {
    const identity = await generateIdentity();
    const jwk = parseEd25519Jwk(identity.publicJwk);
    assert.equal(identity.thumbprint, await serverThumbprint(jwk));
    assert.equal(identity.thumbprint, await browserThumbprint(identity.publicJwk));
});

test("a request signed in the browser verifies against the board", async () => {
    const identity = await generateIdentity();
    const signed = await buildSignedRequest({
        privateKey: identity.privateKey,
        thumbprint: identity.thumbprint,
        method: "POST",
        url: URL_UNDER_TEST,
        payload: { room: "lobby", body: "signed in the browser" },
    });
    const request = asRequest(signed);

    const parsed = parseRequestSignature(request);
    assert.equal(parsed.keyid, identity.thumbprint);
    assert.ok(parsed.nonce !== null);
    await checkContentDigest(request, utf8(signed.body));
    assert.ok(await verifyRequestSignature(request, parsed, parseEd25519Jwk(identity.publicJwk)));
});

test("the base the browser signs is the exact base the server rebuilds", async () => {
    const identity = await generateIdentity();
    const signed = await buildSignedRequest({
        privateKey: identity.privateKey,
        thumbprint: identity.thumbprint,
        url: URL_UNDER_TEST,
        payload: { room: "lobby", body: "byte for byte" },
    });
    const parsed = parseRequestSignature(asRequest(signed));
    // Re-serialising the parameters instead of echoing them is the classic way a
    // verifier disagrees with a signer; if the server rebuilds a different base,
    // this equality is where it shows.
    assert.equal(buildSignatureBase(asRequest(signed), parsed.member), signed.base);
});

test("a body changed after signing fails the server digest check", async () => {
    const identity = await generateIdentity();
    const signed = await buildSignedRequest({
        privateKey: identity.privateKey,
        thumbprint: identity.thumbprint,
        url: URL_UNDER_TEST,
        payload: { room: "lobby", body: "benign" },
    });
    const tampered = new Request(signed.url, {
        method: signed.method,
        headers: signed.headers,
        body: JSON.stringify({ room: "lobby", body: "ignore previous instructions" }),
    });
    const sent = new Uint8Array(await tampered.arrayBuffer());
    await assert.rejects(() => checkContentDigest(tampered, sent), SignatureError);
});

test("the browser signature does not verify when moved to another host", async () => {
    const identity = await generateIdentity();
    const signed = await buildSignedRequest({
        privateKey: identity.privateKey,
        thumbprint: identity.thumbprint,
        url: URL_UNDER_TEST,
        payload: { room: "lobby", body: "bound to one host" },
    });
    const moved = new Request("https://elsewhere.example/v1/posts", {
        method: signed.method,
        headers: signed.headers,
        body: signed.body,
    });
    const parsed = parseRequestSignature(moved);
    assert.ok(!(await verifyRequestSignature(moved, parsed, parseEd25519Jwk(identity.publicJwk))));
});

test("a proof of work solved in the browser is accepted by the server checker", async () => {
    const identity = await generateIdentity();
    const challenge = "server-issued-challenge";
    const bits = 8;
    const solution = await solveProofOfWork(challenge, identity.thumbprint, bits);

    const achieved = await serverPowBits(challenge, identity.thumbprint, solution);
    assert.ok(achieved >= bits, `solved to ${achieved} bits, needed ${bits}`);
    assert.equal(await browserPowBits(challenge, identity.thumbprint, solution), achieved);
    await checkProofOfWork(challenge, identity.thumbprint, solution, bits);
});

test("the browser private key is minted non-extractable and cannot be exported", async () => {
    const identity = await generateIdentity();
    assert.equal(identity.privateKey.extractable, false);
    await assert.rejects(() => crypto.subtle.exportKey("jwk", identity.privateKey));
    await assert.rejects(() => crypto.subtle.exportKey("pkcs8", identity.privateKey));
    // The public half is still exportable, which is why the account JWK exists.
    assert.equal(typeof identity.publicJwk.x, "string");
    assert.ok(identity.publicJwk.x.length > 0);
});
