import { deflateSync } from "node:zlib";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

import { withBrowserPage } from "./browser-cdp.mjs";

export function deterministicMediaFixtures() {
    return [
        { name: "png", mediaType: "image/png", kind: "image", bytes: tinyPng(), source: "generated original 4x4 RGBA PNG" },
        { name: "wav", mediaType: "audio/wav", kind: "audio", bytes: tinyWav(), source: "generated original 1.25s PCM WAV" },
    ];
}

export async function mediaSmokeFixtures(options = {}) {
    const browserOptions = await prepareFixtureBrowserOptions(options);
    return [...deterministicMediaFixtures(), await tinyWebmFromBrowser(browserOptions)];
}

export async function prepareFixtureBrowserOptions(options = {}) {
    if (options.tmpRoot !== undefined) await mkdir(resolve(options.tmpRoot), { recursive: true });
    return { chrome: options.chrome, tmpRoot: options.tmpRoot };
}

export function tinyPng() {
    const rows = [];
    for (let row = 0; row < 4; row += 1) {
        rows.push(0);
        for (let column = 0; column < 4; column += 1) rows.push(0x33, 0x66, 0x99, 0xff);
    }
    const ihdr = [...u32be(4), ...u32be(4), 8, 6, 0, 0, 0];
    return new Uint8Array([
        0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
        ...chunk("IHDR", ihdr),
        ...chunk("IDAT", [...deflateSync(new Uint8Array(rows))]),
        ...chunk("IEND", []),
    ]);
}

export function tinyWav() {
    const sampleRate = 8_000;
    const samples = Math.floor(sampleRate * 1.25);
    const data = [];
    for (let i = 0; i < samples; i += 1) {
        const value = Math.round(Math.sin((i / sampleRate) * 440 * Math.PI * 2) * 12000);
        data.push(value & 0xff, (value >> 8) & 0xff);
    }
    return new Uint8Array([
        ...ascii("RIFF"), ...u32le(36 + data.length), ...ascii("WAVE"),
        ...ascii("fmt "), ...u32le(16), ...u16le(1), ...u16le(1), ...u32le(sampleRate),
        ...u32le(sampleRate * 2), ...u16le(2), ...u16le(16),
        ...ascii("data"), ...u32le(data.length), ...data,
    ]);
}

async function tinyWebmFromBrowser(options) {
    const expression = `new Promise((resolve, reject) => {
        if (!MediaRecorder.isTypeSupported("video/webm;codecs=vp8")) return reject(new Error("video/webm vp8 unsupported"));
        const canvas = document.createElement("canvas");
        canvas.width = 16; canvas.height = 16;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#336699"; ctx.fillRect(0, 0, 16, 16);
        const stream = canvas.captureStream(10);
        const recorder = new MediaRecorder(stream, { mimeType: "video/webm;codecs=vp8" });
        const chunks = [];
        recorder.ondataavailable = (event) => { if (event.data.size > 0) chunks.push(event.data); };
        recorder.onerror = (event) => reject(event.error || new Error("MediaRecorder failed"));
        recorder.onstop = async () => {
            stream.getTracks().forEach((track) => track.stop());
            const bytes = new Uint8Array(await new Blob(chunks, { type: "video/webm" }).arrayBuffer());
            let binary = "";
            for (const byte of bytes) binary += String.fromCharCode(byte);
            resolve({ base64: btoa(binary), bytes: bytes.length });
        };
        let frame = 0;
        const interval = setInterval(() => {
            frame += 1;
            ctx.fillStyle = frame % 2 === 0 ? "#336699" : "#993366";
            ctx.fillRect(0, 0, 16, 16);
        }, 100);
        recorder.start();
        setTimeout(() => { clearInterval(interval); recorder.stop(); }, 1250);
    })`;
    const result = await withBrowserPage(
        (page) => page.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, 15_000),
        { chrome: options.chrome, tmpRoot: options.tmpRoot },
    );
    const value = result.result?.value ?? {};
    const bytes = new Uint8Array(Buffer.from(String(value.base64 ?? ""), "base64"));
    if (bytes.byteLength < 32) throw new Error("browser generated an empty WebM fixture");
    return { name: "webm", mediaType: "video/webm", kind: "video", bytes, source: `generated original ${value.bytes}-byte canvas WebM in Chrome` };
}

function ascii(text) {
    return [...text].map((character) => character.charCodeAt(0));
}

function u16le(value) {
    return [value & 0xff, (value >>> 8) & 0xff];
}

function u32le(value) {
    return [value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff];
}

function u32be(value) {
    return [(value >>> 24) & 0xff, (value >>> 16) & 0xff, (value >>> 8) & 0xff, value & 0xff];
}

const CRC_TABLE = (() => {
    const table = [];
    for (let n = 0; n < 256; n += 1) {
        let c = n;
        for (let k = 0; k < 8; k += 1) c = (c & 1) !== 0 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        table[n] = c >>> 0;
    }
    return table;
})();

function crc32(bytes) {
    let c = 0xffffffff;
    for (const byte of bytes) c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
    const body = [...ascii(type), ...data];
    return [...u32be(data.length), ...body, ...u32be(crc32(body))];
}
