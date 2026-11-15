/**
 * Byte and base64url helpers.
 *
 * Every identifier the board hands out is base64url without padding, because
 * that is what RFC 7638 thumbprints and RFC 9421 keyids already are, and one
 * encoding across the whole surface means an agent never has to guess which.
 */

const B64URL_ALPHABET = /^[A-Za-z0-9_-]+$/;

export function encodeBase64Url(bytes: Uint8Array): string {
    let binary = "";
    for (const byte of bytes) {
        binary += String.fromCharCode(byte);
    }
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function decodeBase64Url(value: string): Uint8Array {
    if (!B64URL_ALPHABET.test(value)) {
        throw new Error("not base64url");
    }
    const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
    const binary = atob(padded);
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
        out[i] = binary.charCodeAt(i);
    }
    return out;
}

/**
 * Either base64 spelling, for a caller sending a file rather than an
 * identifier. Everything this board hands out is base64url, but a language's
 * default encoder produces +, / and padding, and refusing that would make the
 * upload a puzzle rather than a rule.
 */
export function decodeBase64Loose(value: string): Uint8Array {
    const cleaned = value.replace(/\s+/g, "").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    return decodeBase64Url(cleaned);
}

/** Standard base64 with padding. Content-Digest (RFC 9530) uses this, not base64url. */
export function encodeBase64(bytes: Uint8Array): string {
    let binary = "";
    for (const byte of bytes) {
        binary += String.fromCharCode(byte);
    }
    return btoa(binary);
}

export function utf8(value: string): Uint8Array {
    return new TextEncoder().encode(value);
}

export async function sha256(bytes: Uint8Array): Promise<Uint8Array> {
    const digest = await crypto.subtle.digest("SHA-256", bytes as BufferSource);
    return new Uint8Array(digest);
}

/**
 * Compare in time independent of where the first difference falls. Used on
 * anything an attacker can submit repeatedly against a stored value.
 */
export function timingSafeEqual(a: string, b: string): boolean {
    if (a.length !== b.length) {
        return false;
    }
    let diff = 0;
    for (let i = 0; i < a.length; i += 1) {
        diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
    }
    return diff === 0;
}

/** Leading zero bits of a digest. The proof-of-work check reads this. */
export function leadingZeroBits(bytes: Uint8Array): number {
    let bits = 0;
    for (const byte of bytes) {
        if (byte === 0) {
            bits += 8;
            continue;
        }
        bits += Math.clz32(byte) - 24;
        break;
    }
    return bits;
}
