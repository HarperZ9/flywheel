import assert from "node:assert/strict";
import { test } from "node:test";

import {
    decodeBase64Url,
    encodeBase64,
    encodeBase64Url,
    leadingZeroBits,
    sha256,
    timingSafeEqual,
    utf8,
} from "../src/bytes.ts";
import { FLAG_CATEGORIES, isFlagCategory } from "../src/flags.ts";
import { idMillis, newId } from "../src/ids.ts";
import { jwkThumbprint, parseEd25519Jwk } from "../src/jwk.ts";
import { checkProofOfWork, solveProofOfWork } from "../src/pow.ts";
import { eligibleForPromotion, policyFor } from "../src/tiers.ts";

test("base64url round-trips and drops padding", () => {
    const bytes = new Uint8Array([0, 1, 2, 250, 251, 252, 253]);
    const encoded = encodeBase64Url(bytes);
    assert.ok(!encoded.includes("="), "base64url must be unpadded");
    assert.ok(!/[+/]/.test(encoded), "base64url must not use + or /");
    assert.deepEqual(Array.from(decodeBase64Url(encoded)), Array.from(bytes));
});

test("Content-Digest base64 keeps its padding", () => {
    // RFC 9530 carries standard base64 inside the colons, not base64url, and a
    // verifier that confuses the two rejects every well-formed request.
    assert.equal(encodeBase64(new Uint8Array([1, 2, 3])), "AQID");
    assert.equal(encodeBase64(new Uint8Array([1, 2])), "AQI=");
});

test("timingSafeEqual answers on content, not on length alone", () => {
    assert.ok(timingSafeEqual("abc", "abc"));
    assert.ok(!timingSafeEqual("abc", "abd"));
    assert.ok(!timingSafeEqual("abc", "abcd"));
});

test("leadingZeroBits counts across byte boundaries", () => {
    assert.equal(leadingZeroBits(new Uint8Array([0xff])), 0);
    assert.equal(leadingZeroBits(new Uint8Array([0x7f])), 1);
    assert.equal(leadingZeroBits(new Uint8Array([0x01])), 7);
    assert.equal(leadingZeroBits(new Uint8Array([0x00, 0x0f])), 12);
    assert.equal(leadingZeroBits(new Uint8Array([0x00, 0x00])), 16);
});

test("thumbprint matches the RFC 8037 Appendix A.3 vector", async () => {
    // The published vector is the only way to prove the canonicalization is the
    // one every other implementation computes.
    const jwk = parseEd25519Jwk({
        kty: "OKP",
        crv: "Ed25519",
        x: "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
    });
    assert.equal(await jwkThumbprint(jwk), "kPrK_qmxVWaYVA9wwBF6Iuo3vVzz7TxHCTwXBygrS4k");
});

test("a JWK carrying a private key is rejected rather than trimmed", () => {
    assert.throws(() =>
        parseEd25519Jwk({
            kty: "OKP",
            crv: "Ed25519",
            x: "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
            d: "nWGxne_9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A",
        }),
    );
});

test("a short or overlong x is rejected", () => {
    assert.throws(() => parseEd25519Jwk({ kty: "OKP", crv: "Ed25519", x: "AAAA" }));
    assert.throws(() => parseEd25519Jwk({ kty: "EC", crv: "P-256", x: "AAAA" }));
});

test("ids sort by time and carry their timestamp", () => {
    const early = newId(1_700_000_000_000);
    const late = newId(1_700_000_001_000);
    assert.ok(early < late, "ids must sort lexicographically in time order");
    assert.equal(idMillis(early), 1_700_000_000_000);
    assert.equal(idMillis("not-an-id"), null);
});

test("two ids minted in the same millisecond still differ", () => {
    const ids = new Set(Array.from({ length: 200 }, () => newId(1_700_000_000_000)));
    assert.equal(ids.size, 200);
});

test("the flag vocabulary is closed", () => {
    assert.ok(isFlagCategory("injection"));
    assert.ok(!isFlagCategory("spam"));
    assert.ok(!isFlagCategory(""));
    assert.ok(!isFlagCategory(null));
    assert.ok(FLAG_CATEGORIES.includes("credential-request"));
});

test("a solved proof of work verifies and a wrong one does not", async () => {
    const thumbprint = "kPrK_qmxVWaYVA9wwBF6Iuo3vVzz7TxHCTwXBygrS4k";
    const solution = await solveProofOfWork("challenge-1", thumbprint, 12);
    await checkProofOfWork("challenge-1", thumbprint, solution, 12);
    // Same solution, different thumbprint: work done for one key must not
    // transfer to another, or one solve would register a swarm.
    await assert.rejects(() => checkProofOfWork("challenge-1", "other-thumbprint", solution, 12));
    await assert.rejects(() => checkProofOfWork("challenge-2", thumbprint, solution, 12));
});

test("tier policy tightens as trust falls", () => {
    assert.ok(policyFor("probation").postsPerHour < policyFor("verified").postsPerHour);
    assert.ok(policyFor("verified").postsPerHour < policyFor("trusted").postsPerHour);
    assert.equal(policyFor("nonsense").postsPerHour, policyFor("probation").postsPerHour);
    assert.ok(policyFor("probation").provisional);
});

test("promotion needs served time, posts, and a clean flag record", () => {
    const base = {
        tier: "probation" as const,
        firstSeen: 0,
        postCount: 5,
        flagsReceived: 0,
        operatorHost: null,
        nowSeconds: 25 * 3_600,
    };
    assert.ok(eligibleForPromotion(base));
    assert.ok(!eligibleForPromotion({ ...base, nowSeconds: 3_600 }));
    assert.ok(!eligibleForPromotion({ ...base, postCount: 1 }));
    assert.ok(!eligibleForPromotion({ ...base, flagsReceived: 9 }));
    // A verified operator host skips the clock but not the flag record.
    assert.ok(eligibleForPromotion({ ...base, nowSeconds: 60, operatorHost: "bots.example" }));
    assert.ok(
        !eligibleForPromotion({ ...base, nowSeconds: 60, operatorHost: "bots.example", flagsReceived: 9 }),
    );
});

test("sha256 is the digest the rest of the board assumes", async () => {
    const digest = await sha256(utf8("abc"));
    assert.equal(
        encodeBase64(digest),
        "ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0=",
    );
});
