/**
 * The half of rotation that decides whether the receiving key agreed.
 *
 * The outer request proves the old key asked. These tests cover what stops an
 * old key naming a public key whose holder never agreed, which would hand a
 * flagged history to somebody who then has to explain it.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { encodeBase64, utf8 } from "../src/bytes.ts";
import { BoardError } from "../src/errors.ts";
import { ROTATION_CONTEXT, checkCountersignature, rotationStatement } from "../src/rotation.ts";
import { makeSigner, type Signer } from "./helpers.ts";

async function countersign(signer: Signer, from: string, to: string): Promise<string> {
    const raw = await crypto.subtle.sign(
        { name: "Ed25519" },
        signer.privateKey,
        rotationStatement(from, to),
    );
    return encodeBase64(new Uint8Array(raw));
}

/** The thrown BoardError, or a failure if the call was accepted. */
async function rejection(promise: Promise<unknown>): Promise<BoardError> {
    try {
        await promise;
    } catch (error) {
        assert.ok(error instanceof BoardError, `expected a BoardError, got ${String(error)}`);
        return error;
    }
    assert.fail("the countersignature was accepted and should not have been");
}

test("the statement names the version and both thumbprints, in order", () => {
    const bytes = rotationStatement("aaa", "bbb");
    assert.deepEqual(Array.from(bytes), Array.from(utf8(`${ROTATION_CONTEXT}\naaa\nbbb`)));
    // Reversing the pair has to produce different bytes, or a countersignature
    // would verify in the direction nobody agreed to.
    assert.notDeepEqual(Array.from(rotationStatement("bbb", "aaa")), Array.from(bytes));
});

test("the new key's countersignature over its own pair is accepted", async () => {
    const [oldKey, newKey] = await Promise.all([makeSigner(), makeSigner()]);
    const signature = await countersign(newKey, oldKey.thumbprint, newKey.thumbprint);
    await checkCountersignature(oldKey.thumbprint, newKey.thumbprint, newKey.jwk, signature);
});

test("a countersignature lifted from another rotation does not verify", async () => {
    const [oldKey, newKey, stranger] = await Promise.all([makeSigner(), makeSigner(), makeSigner()]);
    // The new key really did agree to take over the stranger's account. That
    // consent must not carry to a rotation out of a different account.
    const elsewhere = await countersign(newKey, stranger.thumbprint, newKey.thumbprint);
    const error = await rejection(
        checkCountersignature(oldKey.thumbprint, newKey.thumbprint, newKey.jwk, elsewhere),
    );
    assert.equal(error.status, 403);
    assert.equal(error.code, "signature_invalid");
});

test("the same pair signed in the other direction does not verify", async () => {
    const [oldKey, newKey] = await Promise.all([makeSigner(), makeSigner()]);
    const backwards = await countersign(newKey, newKey.thumbprint, oldKey.thumbprint);
    const error = await rejection(
        checkCountersignature(oldKey.thumbprint, newKey.thumbprint, newKey.jwk, backwards),
    );
    assert.equal(error.code, "signature_invalid");
});

test("the old key cannot countersign on the new key's behalf", async () => {
    const [oldKey, newKey] = await Promise.all([makeSigner(), makeSigner()]);
    // This is the whole point of the countersignature. The old key already
    // signed the request, so if its signature also satisfied this check the
    // second half would be decoration.
    const forged = await countersign(oldKey, oldKey.thumbprint, newKey.thumbprint);
    const error = await rejection(
        checkCountersignature(oldKey.thumbprint, newKey.thumbprint, newKey.jwk, forged),
    );
    assert.equal(error.status, 403);
    assert.equal(error.code, "signature_invalid");
});

test("a missing countersignature is the caller's mistake, not a signature failure", async () => {
    const [oldKey, newKey] = await Promise.all([makeSigner(), makeSigner()]);
    for (const absent of [undefined, null, "", 42, {}]) {
        const error = await rejection(
            checkCountersignature(oldKey.thumbprint, newKey.thumbprint, newKey.jwk, absent),
        );
        assert.equal(error.status, 400, `${JSON.stringify(absent) ?? "undefined"} should be a 400`);
        assert.equal(error.code, "bad_request");
        assert.match(error.hint, /new key/);
    }
});

test("a countersignature that is not base64 says so rather than failing to verify", async () => {
    const [oldKey, newKey] = await Promise.all([makeSigner(), makeSigner()]);
    const error = await rejection(
        checkCountersignature(oldKey.thumbprint, newKey.thumbprint, newKey.jwk, "not base64 !!"),
    );
    assert.equal(error.status, 400);
    assert.equal(error.code, "bad_request");
});

test("base64url is accepted, because a client that has one encoder has that one", async () => {
    const [oldKey, newKey] = await Promise.all([makeSigner(), makeSigner()]);
    const standard = await countersign(newKey, oldKey.thumbprint, newKey.thumbprint);
    const url = standard.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    await checkCountersignature(oldKey.thumbprint, newKey.thumbprint, newKey.jwk, url);
});

test("a signature of the right length over the wrong bytes is still rejected", async () => {
    const [oldKey, newKey] = await Promise.all([makeSigner(), makeSigner()]);
    const raw = await crypto.subtle.sign(
        { name: "Ed25519" },
        newKey.privateKey,
        utf8(`${oldKey.thumbprint}\n${newKey.thumbprint}`),
    );
    // Both thumbprints, in the right order, without the version line. The
    // context string is what stops a signature made for something else being
    // replayed here, so dropping it has to fail.
    const error = await rejection(
        checkCountersignature(
            oldKey.thumbprint,
            newKey.thumbprint,
            newKey.jwk,
            encodeBase64(new Uint8Array(raw)),
        ),
    );
    assert.equal(error.code, "signature_invalid");
});
