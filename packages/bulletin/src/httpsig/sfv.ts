/**
 * The structured-field parsing a signature check needs, and nothing else.
 *
 * Signature-Input is a dictionary whose members are inner lists of strings with
 * parameters, and Signature is a dictionary of byte sequences. Those are the
 * only two shapes here. A general RFC 8941 parser would accept shapes this code
 * has no use for, and every extra shape it accepted would be surface an
 * attacker could aim at.
 */

import { SignatureError, type SignatureMember } from "./types.ts";

const KEY_START = /[a-z*]/;
const KEY_CHAR = /[a-z0-9_\-.*]/;

/**
 * Parse a structured-field dictionary whose members are inner lists of strings
 * with parameters. That is the shape Signature-Input always takes; a general
 * structured-field parser would accept shapes this code has no use for.
 */
export function parseSignatureInput(input: string): SignatureMember[] {
    const members: SignatureMember[] = [];
    let i = 0;

    const skipSpace = (): void => {
        while (i < input.length && (input[i] === " " || input[i] === "\t")) {
            i += 1;
        }
    };

    const readKey = (): string => {
        const start = i;
        if (i >= input.length || !KEY_START.test(input[i] as string)) {
            throw new SignatureError("malformed Signature-Input", "expected a dictionary key");
        }
        while (i < input.length && KEY_CHAR.test(input[i] as string)) {
            i += 1;
        }
        return input.slice(start, i);
    };

    const readQuoted = (): string => {
        if (input[i] !== '"') {
            throw new SignatureError("malformed Signature-Input", "expected a quoted string");
        }
        i += 1;
        let out = "";
        while (i < input.length) {
            const ch = input[i] as string;
            if (ch === "\\") {
                const next = input[i + 1];
                if (next !== '"' && next !== "\\") {
                    throw new SignatureError("malformed Signature-Input", "bad string escape");
                }
                out += next;
                i += 2;
                continue;
            }
            if (ch === '"') {
                i += 1;
                return out;
            }
            out += ch;
            i += 1;
        }
        throw new SignatureError("malformed Signature-Input", "unterminated string");
    };

    const readParams = (): Map<string, string | number | boolean> => {
        const params = new Map<string, string | number | boolean>();
        while (i < input.length && input[i] === ";") {
            i += 1;
            skipSpace();
            const name = readKey();
            if (input[i] !== "=") {
                // A bare parameter is a boolean true in structured fields.
                params.set(name, true);
                continue;
            }
            i += 1;
            if (input[i] === '"') {
                params.set(name, readQuoted());
                continue;
            }
            const start = i;
            while (i < input.length && /[0-9-]/.test(input[i] as string)) {
                i += 1;
            }
            if (i === start) {
                throw new SignatureError("malformed Signature-Input", `parameter ${name} has no value`);
            }
            const numeric = Number(input.slice(start, i));
            if (!Number.isInteger(numeric)) {
                throw new SignatureError("malformed Signature-Input", `parameter ${name} must be an integer`);
            }
            params.set(name, numeric);
        }
        return params;
    };

    while (i < input.length) {
        skipSpace();
        if (i >= input.length) {
            break;
        }
        const label = readKey();
        if (input[i] !== "=") {
            throw new SignatureError("malformed Signature-Input", `member ${label} has no value`);
        }
        i += 1;
        const rawStart = i;
        if (input[i] !== "(") {
            throw new SignatureError("malformed Signature-Input", "expected an inner list");
        }
        i += 1;
        const covered: string[] = [];
        for (;;) {
            skipSpace();
            if (i >= input.length) {
                throw new SignatureError("malformed Signature-Input", "unterminated inner list");
            }
            if (input[i] === ")") {
                i += 1;
                break;
            }
            covered.push(readQuoted());
            // Component parameters (";req", ";name=") are outside this profile.
            if (input[i] === ";") {
                throw new SignatureError(
                    "unsupported component parameter",
                    "this board covers plain components only",
                );
            }
        }
        const params = readParams();
        members.push({ label, covered, params, raw: input.slice(rawStart, i) });
        skipSpace();
        if (i < input.length) {
            if (input[i] !== ",") {
                throw new SignatureError("malformed Signature-Input", "expected a comma between members");
            }
            i += 1;
        }
    }

    if (members.length === 0) {
        throw new SignatureError("empty Signature-Input", "send one signature");
    }
    return members;
}

/** Parse a Signature header of the form label=:base64: and return one label's bytes. */
export function parseSignatureHeader(input: string, label: string): Uint8Array {
    for (const part of splitTopLevel(input)) {
        const eq = part.indexOf("=");
        if (eq < 0) {
            continue;
        }
        if (part.slice(0, eq).trim() !== label) {
            continue;
        }
        const value = part.slice(eq + 1).trim();
        if (!value.startsWith(":") || !value.endsWith(":") || value.length < 3) {
            throw new SignatureError("malformed Signature", "the value must be a byte sequence");
        }
        try {
            return decodeStandardBase64(value.slice(1, -1));
        } catch {
            throw new SignatureError("malformed Signature", "the byte sequence is not base64");
        }
    }
    throw new SignatureError("Signature has no entry for the signed label", `expected label ${label}`);
}

function splitTopLevel(input: string): string[] {
    const parts: string[] = [];
    let depth = 0;
    let quoted = false;
    let start = 0;
    for (let i = 0; i < input.length; i += 1) {
        const ch = input[i];
        if (quoted) {
            if (ch === "\\") {
                i += 1;
            } else if (ch === '"') {
                quoted = false;
            }
            continue;
        }
        if (ch === '"') {
            quoted = true;
        } else if (ch === "(") {
            depth += 1;
        } else if (ch === ")") {
            depth -= 1;
        } else if (ch === "," && depth === 0) {
            parts.push(input.slice(start, i));
            start = i + 1;
        }
    }
    parts.push(input.slice(start));
    return parts;
}

function decodeStandardBase64(value: string): Uint8Array {
    const binary = atob(value);
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
        out[i] = binary.charCodeAt(i);
    }
    return out;
}

