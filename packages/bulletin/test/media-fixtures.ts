import { deflateSync } from "node:zlib";

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

export interface PngChunk {
    type: string;
    data: readonly number[];
}

export function ascii(text: string): number[] {
    return [...text].map((character) => character.charCodeAt(0));
}

export function u32be(value: number): number[] {
    return [(value >>> 24) & 0xff, (value >>> 16) & 0xff, (value >>> 8) & 0xff, value & 0xff];
}

function crcTable(): number[] {
    const table: number[] = [];
    for (let n = 0; n < 256; n += 1) {
        let c = n;
        for (let k = 0; k < 8; k += 1) {
            c = (c & 1) !== 0 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        }
        table[n] = c >>> 0;
    }
    return table;
}

const CRC_TABLE = crcTable();

function crc32(bytes: readonly number[]): number {
    let c = 0xffffffff;
    for (const byte of bytes) {
        c = CRC_TABLE[(c ^ byte) & 0xff]! ^ (c >>> 8);
    }
    return (c ^ 0xffffffff) >>> 0;
}

export function pngChunk(type: string, data: readonly number[]): number[] {
    const body = [...ascii(type), ...data];
    return [...u32be(data.length), ...body, ...u32be(crc32(body))];
}

export function ihdr(width: number, height: number, bitDepth = 8, colorType = 6): number[] {
    return [...u32be(width), ...u32be(height), bitDepth, colorType, 0, 0, 0];
}

export function pngFromChunks(chunks: readonly PngChunk[]): Uint8Array {
    return new Uint8Array([...PNG_SIGNATURE, ...chunks.flatMap((chunk) => pngChunk(chunk.type, chunk.data))]);
}

export function png(width: number, height: number): Uint8Array {
    const rows: number[] = [];
    for (let row = 0; row < height; row += 1) {
        rows.push(0);
        for (let column = 0; column < width; column += 1) {
            rows.push(0x33, 0x66, 0x99, 0xff);
        }
    }
    const idat = [...deflateSync(new Uint8Array(rows))];
    return pngFromChunks([{ type: "IHDR", data: ihdr(width, height) }, { type: "IDAT", data: idat }, { type: "IEND", data: [] }]);
}

export function indexedPng(): Uint8Array {
    return pngFromChunks([
        { type: "IHDR", data: ihdr(1, 1, 1, 3) },
        { type: "PLTE", data: [0x33, 0x66, 0x99] },
        { type: "IDAT", data: [...deflateSync(new Uint8Array([0, 0]))] },
        { type: "IEND", data: [] },
    ]);
}

export function pngWithoutIdat(width: number, height: number): Uint8Array {
    return pngFromChunks([{ type: "IHDR", data: ihdr(width, height) }, { type: "IEND", data: [] }]);
}

export function pngWithEmptyIdat(width: number, height: number): Uint8Array {
    return pngFromChunks([{ type: "IHDR", data: ihdr(width, height) }, { type: "IDAT", data: [] }, { type: "IEND", data: [] }]);
}

export function liveMalformedPng(): Uint8Array {
    return new Uint8Array([
        ...PNG_SIGNATURE,
        ...u32be(13), ...ascii("IHDR"),
        ...u32be(4), ...u32be(4), 8, 6, 0, 0, 0,
        0, 0, 0, 0,
        ...u32be(0), ...ascii("IEND"), 0xae, 0x42, 0x60, 0x82,
    ]);
}

export function withByte(bytes: Uint8Array, index: number, value: number): Uint8Array {
    const copy = new Uint8Array(bytes);
    copy[index] = value;
    return copy;
}

export function withU32be(bytes: Uint8Array, index: number, value: number): Uint8Array {
    const copy = new Uint8Array(bytes);
    copy.set(u32be(value), index);
    return copy;
}
