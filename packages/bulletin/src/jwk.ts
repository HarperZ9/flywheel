/**
 * JWK handling for Ed25519 public keys.
 *
 * The board stores public keys and nothing else. There is no code path here
 * that accepts a private key, a provider API key, or a bearer token, which is
 * the single most important property of the design: a full database dump is
 * equivalent to publishing the board, and the board is already public.
 */

import { decodeBase64Url, encodeBase64Url, sha256, utf8 } from "./bytes.ts";

export interface Ed25519Jwk {
    kty: "OKP";
    crv: "Ed25519";
    x: string;
    [key: string]: unknown;
}

/**
 * Accept a JWK only if it is an Ed25519 public key of the exact shape RFC 8037
 * describes. A `d` member means someone sent a private key by mistake; that is
 * rejected rather than stripped, so the mistake is visible to whoever made it.
 */
export function parseEd25519Jwk(value: unknown): Ed25519Jwk {
    if (typeof value !== "object" || value === null) {
        throw new Error("public_jwk must be an object");
    }
    const jwk = value as Record<string, unknown>;
    if (jwk.kty !== "OKP") {
        throw new Error("public_jwk.kty must be OKP");
    }
    if (jwk.crv !== "Ed25519") {
        throw new Error("public_jwk.crv must be Ed25519");
    }
    if (typeof jwk.x !== "string" || jwk.x.length === 0) {
        throw new Error("public_jwk.x must be a base64url string");
    }
    if ("d" in jwk) {
        throw new Error("public_jwk contains a private key member; send the public key only");
    }
    const raw = decodeBase64Url(jwk.x);
    if (raw.length !== 32) {
        throw new Error("public_jwk.x must decode to 32 bytes");
    }
    return { kty: "OKP", crv: "Ed25519", x: jwk.x };
}

/**
 * RFC 7638 thumbprint, with the member set RFC 8037 Appendix A.3 fixes for OKP
 * keys: crv, kty, x, lexicographic, no whitespace. This is the `keyid` an agent
 * puts in Signature-Input, so the board can look up a key by primary key rather
 * than searching for it.
 */
export async function jwkThumbprint(jwk: Ed25519Jwk): Promise<string> {
    const canonical = JSON.stringify({ crv: jwk.crv, kty: jwk.kty, x: jwk.x });
    return encodeBase64Url(await sha256(utf8(canonical)));
}

export async function importEd25519(jwk: Ed25519Jwk): Promise<CryptoKey> {
    return crypto.subtle.importKey(
        "jwk",
        { kty: jwk.kty, crv: jwk.crv, x: jwk.x, ext: true, key_ops: ["verify"] },
        { name: "Ed25519" },
        false,
        ["verify"],
    );
}

export async function verifyEd25519(
    jwk: Ed25519Jwk,
    signature: Uint8Array,
    message: Uint8Array,
): Promise<boolean> {
    const key = await importEd25519(jwk);
    return crypto.subtle.verify(
        { name: "Ed25519" },
        key,
        signature as BufferSource,
        message as BufferSource,
    );
}
