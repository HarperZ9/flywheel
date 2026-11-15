import assert from "node:assert/strict";
import { test } from "node:test";

import { sniff } from "../src/media/sniff.ts";
import {
    ascii,
    ihdr,
    indexedPng,
    liveMalformedPng,
    png,
    pngFromChunks,
    pngWithEmptyIdat,
    pngWithoutIdat,
    withByte,
    withU32be,
} from "./media-fixtures.ts";

function refused(bytes: Uint8Array, pattern: RegExp): void {
    assert.throws(
        () => sniff(bytes),
        (error: any) => {
            assert.equal(error.status, 415);
            assert.equal(error.code, "media_unsupported");
            assert.match(error.message, pattern);
            return true;
        },
    );
}

test("a PNG with image data, valid chunk CRCs, and an IEND is accepted", () => {
    const format = sniff(png(4, 4));
    assert.equal(format.type, "image/png");
    assert.equal(format.width, 4);
    assert.equal(format.height, 4);
    assert.equal(format.boundedEnd, true);
});

test("an indexed-color PNG with a palette is accepted", () => {
    const format = sniff(indexedPng());
    assert.equal(format.type, "image/png");
    assert.equal(format.width, 1);
    assert.equal(format.height, 1);
});

test("the live 45 byte PNG fixture is refused", () => {
    refused(liveMalformedPng(), /PNG/);
});

test("a PNG chunk CRC must match the chunk bytes", () => {
    refused(withByte(png(4, 4), 32, 0), /CRC/);
});

test("a PNG must carry image data before IEND", () => {
    refused(pngWithoutIdat(4, 4), /IDAT/);
});

test("a PNG must carry non-empty IDAT image data", () => {
    refused(pngWithEmptyIdat(4, 4), /IDAT/);
});

test("an empty IDAT chunk before image data stays structurally valid", () => {
    const image = pngFromChunks([
        { type: "IHDR", data: ihdr(1, 1) },
        { type: "IDAT", data: [] },
        { type: "IDAT", data: [0x78] },
        { type: "IEND", data: [] },
    ]);
    assert.equal(sniff(image).type, "image/png");
});

test("indexed-color PNGs require a palette before IDAT", () => {
    const image = pngFromChunks([
        { type: "IHDR", data: ihdr(1, 1, 1, 3) },
        { type: "IDAT", data: [0x78] },
        { type: "IEND", data: [] },
    ]);
    refused(image, /PLTE/);
});

test("a PLTE chunk must precede the first IDAT", () => {
    const image = pngFromChunks([
        { type: "IHDR", data: ihdr(1, 1) },
        { type: "IDAT", data: [0x78] },
        { type: "PLTE", data: [0x33, 0x66, 0x99] },
        { type: "IEND", data: [] },
    ]);
    refused(image, /PLTE/);
});

test("a PNG cannot carry more than one PLTE chunk", () => {
    const image = pngFromChunks([
        { type: "IHDR", data: ihdr(1, 1, 1, 3) },
        { type: "PLTE", data: [0, 0, 0] },
        { type: "PLTE", data: [0xff, 0xff, 0xff] },
        { type: "IDAT", data: [0x78] },
        { type: "IEND", data: [] },
    ]);
    refused(image, /PLTE/);
});

test("a PLTE chunk length must describe whole RGB entries", () => {
    const image = pngFromChunks([
        { type: "IHDR", data: ihdr(1, 1, 1, 3) },
        { type: "PLTE", data: [0, 0, 0, 0] },
        { type: "IDAT", data: [0x78] },
        { type: "IEND", data: [] },
    ]);
    refused(image, /PLTE/);
});

test("a PLTE chunk cannot be empty or exceed 256 entries", () => {
    const empty = pngFromChunks([
        { type: "IHDR", data: ihdr(1, 1, 1, 3) },
        { type: "PLTE", data: [] },
        { type: "IDAT", data: [0x78] },
        { type: "IEND", data: [] },
    ]);
    const tooLarge = pngFromChunks([
        { type: "IHDR", data: ihdr(1, 1, 8, 3) },
        { type: "PLTE", data: new Array(771).fill(0) },
        { type: "IDAT", data: [0x78] },
        { type: "IEND", data: [] },
    ]);
    refused(empty, /PLTE/);
    refused(tooLarge, /PLTE/);
});

test("indexed PLTE entries cannot exceed the bit depth range", () => {
    const image = pngFromChunks([
        { type: "IHDR", data: ihdr(1, 1, 1, 3) },
        { type: "PLTE", data: [0, 0, 0, 1, 1, 1, 2, 2, 2] },
        { type: "IDAT", data: [0x78] },
        { type: "IEND", data: [] },
    ]);
    refused(image, /PLTE/);
});

test("PLTE is not valid for grayscale PNGs", () => {
    const image = pngFromChunks([
        { type: "IHDR", data: ihdr(1, 1, 8, 0) },
        { type: "PLTE", data: [0, 0, 0] },
        { type: "IDAT", data: [0x78] },
        { type: "IEND", data: [] },
    ]);
    refused(image, /PLTE/);
});

test("unknown critical PNG chunks are refused", () => {
    const image = pngFromChunks([
        { type: "IHDR", data: ihdr(1, 1) },
        { type: "ABCD", data: [] },
        { type: "IDAT", data: [0x78] },
        { type: "IEND", data: [] },
    ]);
    refused(image, /critical/);
});

test("unknown ancillary PNG chunks with valid structure are allowed", () => {
    const image = pngFromChunks([
        { type: "IHDR", data: ihdr(1, 1) },
        { type: "aaAa", data: [0] },
        { type: "IDAT", data: [0x78] },
        { type: "IEND", data: [] },
    ]);
    assert.equal(sniff(image).type, "image/png");
});

test("PNG chunk type reserved bits must be zero", () => {
    const image = pngFromChunks([
        { type: "IHDR", data: ihdr(1, 1) },
        { type: "aaca", data: [] },
        { type: "IDAT", data: [0x78] },
        { type: "IEND", data: [] },
    ]);
    refused(image, /reserved/);
});

test("a PNG chunk length cannot point past the uploaded bytes", () => {
    refused(withU32be(png(4, 4), 33, 0x7fffffff), /chunk length/);
});

test("a PNG chunk length cannot exceed the signed 31 bit bound", () => {
    refused(withU32be(png(4, 4), 33, 0x80000000), /chunk length/);
});

test("a truncated PNG is refused as incomplete", () => {
    refused(png(4, 4).slice(0, 41), /incomplete/);
});

test("a PNG cannot advertise zero dimensions", () => {
    refused(pngWithoutIdat(0, 4), /dimensions/);
});

test("a PNG dimension cannot exceed the signed 31 bit bound", () => {
    const image = pngFromChunks([
        { type: "IHDR", data: ihdr(0x80000000, 1) },
        { type: "IDAT", data: [0x78] },
        { type: "IEND", data: [] },
    ]);
    refused(image, /dimensions/);
});

test("data after the parsed IEND chunk is refused", () => {
    refused(new Uint8Array([...png(4, 4), ...ascii("PK")]), /IEND/);
});
