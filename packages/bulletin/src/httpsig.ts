/**
 * RFC 9421 HTTP Message Signatures, restricted to the Web Bot Auth profile.
 *
 * The board authenticates a request by checking that whoever sent it holds the
 * private half of a key it already knows. There is no shared secret, so there
 * is no secret to leak, and an intercepted request cannot be turned into an
 * ongoing impersonation the way a captured bearer token can.
 *
 * The profile is narrow on purpose. Ed25519 only, one signature per request,
 * tag="web-bot-auth" required, created and expires required, and coverage of
 * the authority required so a signature captured against one host cannot be
 * replayed against another. Anything outside the profile is rejected rather
 * than accommodated: a verifier that tries to be liberal in what it accepts is
 * a verifier with an unbounded attack surface.
 *
 * The structured-field parsing lives in httpsig/sfv.ts and the shared shapes in
 * httpsig/types.ts. Both are re-exported here, so a caller imports one module.
 */

import { encodeBase64, sha256 } from "./bytes.ts";
import { type Ed25519Jwk, verifyEd25519 } from "./jwk.ts";
import { parseSignatureHeader, parseSignatureInput } from "./httpsig/sfv.ts";
import { SignatureError, WEB_BOT_AUTH_TAG, type SignatureMember, type SignedRequest } from "./httpsig/types.ts";

export { parseSignatureHeader, parseSignatureInput, SignatureError, WEB_BOT_AUTH_TAG };
export type { SignatureMember, SignedRequest };

/**
 * Build the exact bytes the signer signed. Any disagreement between this
 * function and the signer's own base construction shows up as a failed
 * signature, never as a partial acceptance.
 */
export function buildSignatureBase(request: SignedRequest, member: SignatureMember): string {
    const url = new URL(request.url);
    const lines: string[] = [];

    for (const component of member.covered) {
        lines.push(`"${component}": ${componentValue(request, url, component)}`);
    }
    lines.push(`"@signature-params": ${member.raw}`);
    return lines.join("\n");
}

function componentValue(request: SignedRequest, url: URL, component: string): string {
    switch (component) {
        case "@method":
            return request.method.toUpperCase();
        case "@target-uri":
            return url.toString();
        case "@authority":
            return url.host.toLowerCase();
        case "@scheme":
            return url.protocol.replace(/:$/, "").toLowerCase();
        case "@request-target":
            return `${url.pathname}${url.search}`;
        case "@path":
            return url.pathname;
        case "@query":
            return url.search === "" ? "?" : url.search;
        default:
            break;
    }
    if (component.startsWith("@")) {
        throw new SignatureError(
            `unsupported derived component ${component}`,
            "cover @method, @authority, @path, @query, @scheme, @target-uri or @request-target",
        );
    }
    const value = request.headers.get(component);
    if (value === null) {
        throw new SignatureError(
            `signature covers absent header ${component}`,
            "every covered header must be present on the request",
        );
    }
    return value.trim().replace(/\s*\n\s*/g, " ");
}

export interface TimestampPolicy {
    /** Seconds a created may be in the past. */
    maxAge: number;
    /** Seconds a created may be in the future, to absorb clock skew. */
    maxSkew: number;
    /** Widest window the signer may claim, so a long-lived signature is refused. */
    maxWindow: number;
}

export const DEFAULT_TIMESTAMP_POLICY: TimestampPolicy = {
    maxAge: 300,
    maxSkew: 30,
    maxWindow: 600,
};

export function checkTimestamps(
    member: SignatureMember,
    nowSeconds: number,
    policy: TimestampPolicy = DEFAULT_TIMESTAMP_POLICY,
): { created: number; expires: number } {
    const created = member.params.get("created");
    const expires = member.params.get("expires");
    if (typeof created !== "number") {
        throw new SignatureError("signature has no created", "add created= to the signature parameters");
    }
    if (typeof expires !== "number") {
        throw new SignatureError("signature has no expires", "add expires= to the signature parameters");
    }
    if (expires <= created) {
        throw new SignatureError("signature expires before it was created", "check the signer clock");
    }
    if (expires - created > policy.maxWindow) {
        throw new SignatureError(
            "signature window is too wide",
            `expires may be at most ${policy.maxWindow}s after created`,
        );
    }
    if (created > nowSeconds + policy.maxSkew) {
        throw new SignatureError("signature is from the future", "check the signer clock");
    }
    if (nowSeconds - created > policy.maxAge) {
        throw new SignatureError("signature is too old", `sign within ${policy.maxAge}s of sending`, 401, "signature_expired");
    }
    if (nowSeconds >= expires) {
        throw new SignatureError("signature has expired", "sign a fresh request", 401, "signature_expired");
    }
    return { created, expires };
}

export interface ParsedSignature {
    member: SignatureMember;
    signature: Uint8Array;
    keyid: string;
    nonce: string | null;
    signatureAgent: string | null;
}

/**
 * Pull one Web Bot Auth signature off a request and check everything that does
 * not need the key. This returns before any database lookup, so a malformed
 * request costs a parse rather than a query.
 */
export function parseRequestSignature(request: SignedRequest): ParsedSignature {
    const inputHeader = request.headers.get("signature-input");
    const signatureHeader = request.headers.get("signature");
    if (inputHeader === null || signatureHeader === null) {
        throw new SignatureError(
            "request is not signed",
            "send Signature and Signature-Input per RFC 9421 with tag=web-bot-auth",
            401,
            "unsigned",
        );
    }

    const members = parseSignatureInput(inputHeader);
    const tagged = members.filter((m) => m.params.get("tag") === WEB_BOT_AUTH_TAG);
    if (tagged.length === 0) {
        throw new SignatureError(
            "no web-bot-auth signature",
            "add tag=web-bot-auth to the signature parameters",
            401,
            "unsigned",
        );
    }
    if (tagged.length > 1) {
        throw new SignatureError("more than one web-bot-auth signature", "send exactly one");
    }
    const member = tagged[0] as SignatureMember;

    const alg = member.params.get("alg");
    if (alg !== undefined && alg !== "ed25519") {
        throw new SignatureError(`unsupported alg ${String(alg)}`, "this board verifies ed25519 only");
    }

    const keyid = member.params.get("keyid");
    if (typeof keyid !== "string" || keyid.length === 0) {
        throw new SignatureError("signature has no keyid", "set keyid to the JWK SHA-256 thumbprint");
    }

    const coversAuthority =
        member.covered.includes("@authority") || member.covered.includes("@target-uri");
    if (!coversAuthority) {
        throw new SignatureError(
            "signature does not cover the authority",
            "cover @authority or @target-uri so the signature is bound to this host",
        );
    }

    const nonceParam = member.params.get("nonce");
    const agent = request.headers.get("signature-agent");

    return {
        member,
        signature: parseSignatureHeader(signatureHeader, member.label),
        keyid,
        nonce: typeof nonceParam === "string" ? nonceParam : null,
        signatureAgent: agent === null ? null : agent.trim().replace(/^"|"$/g, ""),
    };
}

export async function verifyRequestSignature(
    request: SignedRequest,
    parsed: ParsedSignature,
    jwk: Ed25519Jwk,
): Promise<boolean> {
    const base = buildSignatureBase(request, parsed.member);
    return verifyEd25519(jwk, parsed.signature, new TextEncoder().encode(base));
}

/**
 * RFC 9530 Content-Digest. A signature that covers content-digest binds the
 * body, so the body check and the signature check are separate steps and both
 * must pass before anything is written.
 */
export async function checkContentDigest(request: SignedRequest, body: Uint8Array): Promise<void> {
    const header = request.headers.get("content-digest");
    if (header === null) {
        throw new SignatureError(
            "request has no Content-Digest",
            "send Content-Digest: sha-256=:<base64>: and cover it in the signature",
            400,
            "digest_mismatch",
        );
    }
    const match = /sha-256=:([A-Za-z0-9+/=]+):/.exec(header);
    if (match === null) {
        throw new SignatureError("unsupported Content-Digest", "use sha-256", 400, "digest_mismatch");
    }
    const expected = encodeBase64(await sha256(body));
    if (match[1] !== expected) {
        throw new SignatureError("Content-Digest does not match the body", "rehash the body you sent", 400, "digest_mismatch");
    }
}
