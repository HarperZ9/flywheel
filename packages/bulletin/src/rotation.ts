/**
 * The statement two keys sign to move one account between them.
 *
 * The outer request is signed by the old key, which proves the account holder
 * asked for this. That alone is not enough. An old key could name any public
 * key it liked, including one belonging to somebody who never agreed, and hand
 * a flagged history to an innocent party who then has to explain it.
 *
 * So the new key countersigns a statement naming both thumbprints. Both halves
 * consent, and neither signature means anything away from this pair: the
 * statement carries the old thumbprint and the new one, so a countersignature
 * lifted from one rotation verifies against no other.
 *
 * Freshness is the outer request's job. It carries a nonce that is spent once
 * and a signature window that closes, so replaying a whole rotation fails
 * before this code runs. Adding a second clock here would be a second thing to
 * get wrong.
 */

import { decodeBase64Loose, utf8 } from "./bytes.ts";
import { BoardError } from "./errors.ts";
import { verifyEd25519, type Ed25519Jwk } from "./jwk.ts";

/** Versioned, so a later statement shape cannot be verified as this one. */
export const ROTATION_CONTEXT = "bulletin-key-rotation/v1";

/**
 * The exact bytes the new key signs. Newline separated and nothing else, so a
 * client can build it in three lines without a canonicalisation library.
 */
export function rotationStatement(from: string, to: string): Uint8Array {
    return utf8(`${ROTATION_CONTEXT}\n${from}\n${to}`);
}

/**
 * Whether the holder of `newJwk` agreed to receive the account held by `from`.
 *
 * Throws rather than returning false, because every caller would otherwise
 * write the same rejection, and a caller that forgot would accept a rotation
 * nobody countersigned.
 */
export async function checkCountersignature(
    from: string,
    to: string,
    newJwk: Ed25519Jwk,
    countersignature: unknown,
): Promise<void> {
    if (typeof countersignature !== "string" || countersignature.length === 0) {
        throw new BoardError(
            400,
            "bad_request",
            "countersignature is missing",
            `sign "${ROTATION_CONTEXT}\\n<old thumbprint>\\n<new thumbprint>" with the new key, base64`,
        );
    }
    let raw: Uint8Array;
    try {
        raw = decodeBase64Loose(countersignature);
    } catch {
        throw new BoardError(
            400,
            "bad_request",
            "countersignature is not base64",
            "send the raw 64-byte Ed25519 signature, base64 or base64url",
        );
    }
    if (!(await verifyEd25519(newJwk, raw, rotationStatement(from, to)))) {
        throw new BoardError(
            403,
            "signature_invalid",
            "countersignature does not verify under the new key",
            "the new key must sign the statement naming both thumbprints, in that order",
        );
    }
}
