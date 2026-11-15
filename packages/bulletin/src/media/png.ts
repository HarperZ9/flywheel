import { at, malformed, starts, u32be } from "./read.ts";
import type { Format } from "./read.ts";

const PNG_SIGNATURE = "\x89PNG\r\n\x1a\n";
const MAX_DIMENSION = 0x7fffffff;
const MAX_CHUNK_LENGTH = 0x7fffffff;
const MAX_PLTE_BYTES = 256 * 3;
const KNOWN_CRITICAL = new Set(["IHDR", "PLTE", "IDAT", "IEND"]);

const VALID_DEPTHS = new Map<number, readonly number[]>([
    [0, [1, 2, 4, 8, 16]],
    [2, [8, 16]],
    [3, [1, 2, 4, 8]],
    [4, [8, 16]],
    [6, [8, 16]],
]);

interface Chunk {
    offset: number;
    length: number;
    type: string;
    dataStart: number;
    dataEnd: number;
    next: number;
}

interface Ihdr {
    width: number;
    height: number;
    bitDepth: number;
    colorType: number;
}

function crcTable(): Uint32Array {
    const table = new Uint32Array(256);
    for (let n = 0; n < table.length; n += 1) {
        let c = n;
        for (let k = 0; k < 8; k += 1) {
            c = (c & 1) !== 0 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        }
        table[n] = c >>> 0;
    }
    return table;
}

const CRC_TABLE = crcTable();

function crc32(bytes: Uint8Array, start: number, end: number): number {
    let c = 0xffffffff;
    for (let i = start; i < end; i += 1) {
        c = CRC_TABLE[(c ^ at(bytes, i)) & 0xff]! ^ (c >>> 8);
    }
    return (c ^ 0xffffffff) >>> 0;
}

function chunkType(bytes: Uint8Array, offset: number): string {
    const codes = [at(bytes, offset), at(bytes, offset + 1), at(bytes, offset + 2), at(bytes, offset + 3)];
    if (!codes.every((code) => (code >= 0x41 && code <= 0x5a) || (code >= 0x61 && code <= 0x7a))) {
        malformed("PNG chunk type is not four ASCII letters", "send a complete PNG");
    }
    if ((codes[2]! & 0x20) !== 0) {
        malformed("PNG chunk type reserved bit must be zero", "send a PNG file conforming to PNG 1.0");
    }
    return String.fromCharCode(...codes);
}

function critical(type: string): boolean {
    return (type.charCodeAt(0) & 0x20) === 0;
}

function readChunk(bytes: Uint8Array, offset: number): Chunk {
    if (offset + 12 > bytes.length) {
        malformed("PNG chunk header is incomplete", "send a complete PNG");
    }
    const length = u32be(bytes, offset);
    if (length > MAX_CHUNK_LENGTH) {
        malformed("PNG chunk length exceeds 2^31-1", "send a complete PNG");
    }
    const dataStart = offset + 8;
    if (length > bytes.length - dataStart - 4) {
        malformed("PNG chunk length extends past the uploaded bytes", "send a complete PNG");
    }
    const dataEnd = dataStart + length;
    return { offset, length, type: chunkType(bytes, offset + 4), dataStart, dataEnd, next: dataEnd + 4 };
}

function checkCrc(bytes: Uint8Array, chunk: Chunk): void {
    const expected = u32be(bytes, chunk.dataEnd);
    const actual = crc32(bytes, chunk.offset + 4, chunk.dataEnd);
    if (actual !== expected) {
        malformed(`PNG ${chunk.type} chunk CRC does not match`, "send a complete PNG");
    }
}

function checkIhdr(bytes: Uint8Array, chunk: Chunk): Ihdr {
    if (chunk.type !== "IHDR" || chunk.length !== 13) {
        malformed("PNG header is not an IHDR chunk", "send a complete PNG");
    }
    checkCrc(bytes, chunk);
    const width = u32be(bytes, chunk.dataStart);
    const height = u32be(bytes, chunk.dataStart + 4);
    if (width === 0 || height === 0 || width > MAX_DIMENSION || height > MAX_DIMENSION) {
        malformed("PNG dimensions must be from 1 through 2^31-1", "send a complete PNG");
    }
    checkIhdrFields(bytes, chunk.dataStart);
    return { width, height, bitDepth: at(bytes, chunk.dataStart + 8), colorType: at(bytes, chunk.dataStart + 9) };
}

function checkIhdrFields(bytes: Uint8Array, start: number): void {
    const bitDepth = at(bytes, start + 8);
    const colorType = at(bytes, start + 9);
    const validDepths = VALID_DEPTHS.get(colorType);
    if (validDepths === undefined || !validDepths.includes(bitDepth)) {
        malformed("PNG IHDR bit depth and color type are not a valid pair", "send a complete PNG");
    }
    if (at(bytes, start + 10) !== 0 || at(bytes, start + 11) !== 0) {
        malformed("PNG IHDR compression and filter methods must be zero", "send a complete PNG");
    }
    if (at(bytes, start + 12) > 1) {
        malformed("PNG IHDR interlace method is not valid", "send a complete PNG");
    }
}

function checkKnownCritical(chunk: Chunk): void {
    if (critical(chunk.type) && !KNOWN_CRITICAL.has(chunk.type)) {
        malformed(`PNG critical chunk ${chunk.type} is not understood`, "send a PNG using only standard critical chunks");
    }
}

function checkPlte(chunk: Chunk, ihdr: Ihdr, sawIdat: boolean, sawPlte: boolean): void {
    if (sawPlte) {
        malformed("PNG carries more than one PLTE chunk", "send a complete PNG");
    }
    if (sawIdat) {
        malformed("PNG PLTE chunk must precede IDAT", "send a complete PNG");
    }
    if (ihdr.colorType === 0 || ihdr.colorType === 4) {
        malformed("PNG PLTE chunk is not valid for grayscale color types", "send a complete PNG");
    }
    if (chunk.length === 0 || chunk.length % 3 !== 0 || chunk.length > MAX_PLTE_BYTES) {
        malformed("PNG PLTE chunk must contain 1 to 256 RGB entries", "send a complete PNG");
    }
    const entries = chunk.length / 3;
    if (ihdr.colorType === 3 && entries > 2 ** ihdr.bitDepth) {
        malformed("PNG PLTE entries exceed the indexed bit depth", "send a complete PNG");
    }
}

export function png(bytes: Uint8Array): Format | null {
    if (!starts(bytes, PNG_SIGNATURE)) {
        return null;
    }
    let chunk = readChunk(bytes, PNG_SIGNATURE.length);
    const ihdr = checkIhdr(bytes, chunk);
    let sawIdat = false;
    let idatBytes = 0;
    let idatClosed = false;
    let sawPlte = false;
    while (chunk.next < bytes.length) {
        chunk = readChunk(bytes, chunk.next);
        checkCrc(bytes, chunk);
        checkKnownCritical(chunk);
        if (chunk.type === "IHDR") {
            malformed("PNG carries more than one IHDR chunk", "send a complete PNG");
        }
        if (chunk.type === "PLTE") {
            checkPlte(chunk, ihdr, sawIdat, sawPlte);
            sawPlte = true;
        }
        if (chunk.type === "IDAT") {
            if (idatClosed) {
                malformed("PNG IDAT chunks must be consecutive", "send a complete PNG");
            }
            sawIdat = true;
            idatBytes += chunk.length;
        } else if (sawIdat) {
            idatClosed = true;
        }
        if (chunk.type === "IEND") {
            if (chunk.length !== 0) {
                malformed("PNG IEND chunk must be empty", "send a complete PNG");
            }
            if (!sawIdat || idatBytes === 0) {
                malformed("PNG carries no IDAT image data", "send a complete PNG");
            }
            if (ihdr.colorType === 3 && !sawPlte) {
                malformed("PNG indexed color requires a PLTE chunk", "send a complete PNG");
            }
            if (chunk.next !== bytes.length) {
                malformed("PNG does not end at its IEND chunk", "strip whatever follows the end of the image");
            }
            return { type: "image/png", extension: "png", kind: "image", boundedEnd: true, width: ihdr.width, height: ihdr.height };
        }
    }
    malformed("PNG does not end at its IEND chunk", "send a complete PNG");
}
