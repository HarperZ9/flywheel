/**
 * Reading fields out of a container header.
 *
 * A recognizer needs to pull a handful of integers out of bytes it has not
 * validated yet, so every read here is bounds-safe and returns zero past the
 * end rather than throwing. A short file then fails its format's own structure
 * check, which is a better error than an index crash.
 */

import { BoardError } from "../errors.ts";

export type MediaKind = "image" | "audio" | "video";

export interface Format {
    /** The type the board will serve these bytes as, whatever the sender called them. */
    type: string;
    /** Extension for the inline filename, so a saved file opens in the right thing. */
    extension: string;
    kind: MediaKind;
    /** True when the container states where it ends and the end was checked. */
    boundedEnd: boolean;
    width: number | null;
    height: number | null;
}

export function malformed(what: string, hint: string): never {
    throw new BoardError(415, "media_unsupported", what, hint);
}

export function at(bytes: Uint8Array, index: number): number {
    return bytes[index] ?? 0;
}

export function starts(bytes: Uint8Array, signature: string, offset = 0): boolean {
    if (bytes.length < offset + signature.length) {
        return false;
    }
    for (let i = 0; i < signature.length; i += 1) {
        if (at(bytes, offset + i) !== signature.charCodeAt(i)) {
            return false;
        }
    }
    return true;
}

export function u16be(bytes: Uint8Array, index: number): number {
    return at(bytes, index) * 0x100 + at(bytes, index + 1);
}

export function u16le(bytes: Uint8Array, index: number): number {
    return at(bytes, index) + at(bytes, index + 1) * 0x100;
}

export function u24le(bytes: Uint8Array, index: number): number {
    return at(bytes, index) + at(bytes, index + 1) * 0x100 + at(bytes, index + 2) * 0x10000;
}

export function u32be(bytes: Uint8Array, index: number): number {
    return at(bytes, index) * 0x1000000 + at(bytes, index + 1) * 0x10000 + at(bytes, index + 2) * 0x100 + at(bytes, index + 3);
}

export function u32le(bytes: Uint8Array, index: number): number {
    return at(bytes, index) + at(bytes, index + 1) * 0x100 + at(bytes, index + 2) * 0x10000 + at(bytes, index + 3) * 0x1000000;
}

/** ASCII within a bounded prefix. Used to read a container's own codec label. */
export function labelled(bytes: Uint8Array, label: string, within: number): boolean {
    const limit = Math.min(bytes.length, within);
    for (let i = 0; i + label.length <= limit; i += 1) {
        if (starts(bytes, label, i)) {
            return true;
        }
    }
    return false;
}
