/**
 * What each accepted container looks like from the outside.
 *
 * One recognizer per format. A recognizer returns null when the bytes are not
 * that format at all, and throws when they open like that format and then fail
 * its own structure. The second case is worth an error rather than a shrug: a
 * poster whose PNG has a zip stapled to the end should be told that is why.
 *
 * Nothing here decodes an image. The checks read the container: signatures,
 * declared sizes, structural markers, CRCs where the format carries them, and
 * the dimensions the header states. That catches a file renamed into an allowed
 * type and catches data appended after the format ends. It does not catch a
 * payload hidden inside pixels, and the board does not claim it does.
 */

import { png } from "./png.ts";
import { at, labelled, malformed, starts, u16be, u16le, u24le, u32be, u32le } from "./read.ts";
import type { Format } from "./read.ts";

export type { Format, MediaKind } from "./read.ts";
export { png };

/* ------------------------------------------------------------------- PNG */

/* ------------------------------------------------------------------- GIF */

export function gif(bytes: Uint8Array): Format | null {
    if (!starts(bytes, "GIF87a") && !starts(bytes, "GIF89a")) {
        return null;
    }
    if (bytes.length < 14) {
        malformed("GIF is shorter than its own header", "send a complete GIF");
    }
    if (at(bytes, bytes.length - 1) !== 0x3b) {
        malformed("GIF does not end at its trailer", "strip whatever follows the end of the image");
    }
    return {
        type: "image/gif",
        extension: "gif",
        kind: "image",
        boundedEnd: true,
        width: u16le(bytes, 6),
        height: u16le(bytes, 8),
    };
}

/* ------------------------------------------------------------------ JPEG */

const SOF_SKIP = new Set([0xc4, 0xc8, 0xcc]);

export function jpeg(bytes: Uint8Array): Format | null {
    if (at(bytes, 0) !== 0xff || at(bytes, 1) !== 0xd8 || at(bytes, 2) !== 0xff) {
        return null;
    }
    if (at(bytes, bytes.length - 2) !== 0xff || at(bytes, bytes.length - 1) !== 0xd9) {
        malformed("JPEG does not end at its EOI marker", "strip whatever follows the end of the image");
    }
    // Walk the marker segments to the first frame header, which is where the
    // real dimensions are. Entropy-coded data is not scanned: reaching a scan
    // without a frame header means the file has no frame at all.
    let cursor = 2;
    for (let step = 0; step < 512 && cursor + 4 <= bytes.length; step += 1) {
        if (at(bytes, cursor) !== 0xff) {
            break;
        }
        const marker = at(bytes, cursor + 1);
        if (marker === 0xff) {
            cursor += 1;
            continue;
        }
        if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) {
            cursor += 2;
            continue;
        }
        if (marker === 0xda || marker === 0xd9) {
            break;
        }
        const length = u16be(bytes, cursor + 2);
        if (length < 2) {
            malformed("JPEG segment declares an impossible length", "send a complete JPEG");
        }
        if (marker >= 0xc0 && marker <= 0xcf && !SOF_SKIP.has(marker)) {
            return {
                type: "image/jpeg",
                extension: "jpg",
                kind: "image",
                boundedEnd: true,
                height: u16be(bytes, cursor + 5),
                width: u16be(bytes, cursor + 7),
            };
        }
        cursor += 2 + length;
    }
    malformed("JPEG carries no frame header", "send a complete JPEG");
}

/* ------------------------------------------------------- RIFF: WebP, WAV */

export function riff(bytes: Uint8Array): Format | null {
    if (!starts(bytes, "RIFF")) {
        return null;
    }
    if (bytes.length < 20) {
        malformed("RIFF file is shorter than its own header", "send a complete file");
    }
    // The declared size is the whole file minus the eight bytes that carry it.
    // Checking it is what makes appended data a rejection rather than a payload.
    if (u32le(bytes, 4) + 8 !== bytes.length) {
        malformed("RIFF size does not match the bytes sent", "strip whatever follows the end of the file");
    }
    if (starts(bytes, "WAVE", 8)) {
        return { type: "audio/wav", extension: "wav", kind: "audio", boundedEnd: true, width: null, height: null };
    }
    if (!starts(bytes, "WEBP", 8)) {
        malformed("RIFF file is neither WAVE nor WEBP", "send a WebP image or a WAV file");
    }
    const size = webpSize(bytes);
    return {
        type: "image/webp",
        extension: "webp",
        kind: "image",
        boundedEnd: true,
        width: size?.width ?? null,
        height: size?.height ?? null,
    };
}

/** WebP states its canvas in whichever of three chunk kinds opens the file. */
function webpSize(bytes: Uint8Array): { width: number; height: number } | null {
    if (starts(bytes, "VP8X", 12)) {
        return { width: u24le(bytes, 24) + 1, height: u24le(bytes, 27) + 1 };
    }
    if (starts(bytes, "VP8L", 12) && at(bytes, 20) === 0x2f) {
        const packed = u32le(bytes, 21);
        return { width: (packed & 0x3fff) + 1, height: ((packed >>> 14) & 0x3fff) + 1 };
    }
    if (starts(bytes, "VP8 ", 12) && at(bytes, 23) === 0x9d && at(bytes, 24) === 0x01 && at(bytes, 25) === 0x2a) {
        return { width: u16le(bytes, 26) & 0x3fff, height: u16le(bytes, 28) & 0x3fff };
    }
    return null;
}

/* ------------------------------------------------- ISO-BMFF: AVIF, MP4, M4A */

const MP4_BRANDS = new Set(["isom", "iso2", "iso4", "iso6", "mp41", "mp42", "avc1", "dash", "M4V "]);

export function isoBmff(bytes: Uint8Array): Format | null {
    if (!starts(bytes, "ftyp", 4)) {
        return null;
    }
    const declared = u32be(bytes, 0);
    if (declared < 16 || declared > bytes.length) {
        malformed("ISO base media header declares an impossible size", "send a complete file");
    }
    const brand = String.fromCharCode(at(bytes, 8), at(bytes, 9), at(bytes, 10), at(bytes, 11));
    // Dimensions stay null throughout: these containers state them inside a
    // track or item box, and the board reads headers rather than parsing a tree.
    if (brand === "avif" || brand === "avis") {
        return { type: "image/avif", extension: "avif", kind: "image", boundedEnd: false, width: null, height: null };
    }
    if (brand === "M4A ") {
        return { type: "audio/mp4", extension: "m4a", kind: "audio", boundedEnd: false, width: null, height: null };
    }
    if (MP4_BRANDS.has(brand)) {
        return { type: "video/mp4", extension: "mp4", kind: "video", boundedEnd: false, width: null, height: null };
    }
    malformed(`ISO base media brand ${brand.trim()} is not accepted`, "send AVIF, MP4, or M4A");
}

/* --------------------------------------------------------------- Matroska */

export function webm(bytes: Uint8Array): Format | null {
    if (at(bytes, 0) !== 0x1a || at(bytes, 1) !== 0x45 || at(bytes, 2) !== 0xdf || at(bytes, 3) !== 0xa3) {
        return null;
    }
    // Matroska and WebM share a container. Only the WebM profile is accepted,
    // and the file says which it is in its own DocType element.
    if (!labelled(bytes, "webm", 64)) {
        malformed("Matroska file is not a WebM", "send a WebM");
    }
    return { type: "video/webm", extension: "webm", kind: "video", boundedEnd: false, width: null, height: null };
}

/* -------------------------------------------------------------- Ogg, FLAC */

const OGG_CODECS = ["OpusHead", "vorbis", "Speex", "FLAC"];

export function ogg(bytes: Uint8Array): Format | null {
    if (!starts(bytes, "OggS")) {
        return null;
    }
    if (!OGG_CODECS.some((codec) => labelled(bytes, codec, 128))) {
        malformed("Ogg stream carries no audio codec the board accepts", "send Opus, Vorbis, Speex, or Ogg FLAC");
    }
    return { type: "audio/ogg", extension: "ogg", kind: "audio", boundedEnd: false, width: null, height: null };
}

export function flac(bytes: Uint8Array): Format | null {
    if (!starts(bytes, "fLaC")) {
        return null;
    }
    return { type: "audio/flac", extension: "flac", kind: "audio", boundedEnd: false, width: null, height: null };
}

/* -------------------------------------------------------------------- MP3 */

export function mp3(bytes: Uint8Array): Format | null {
    const audio: Format = {
        type: "audio/mpeg",
        extension: "mp3",
        kind: "audio",
        boundedEnd: false,
        width: null,
        height: null,
    };
    if (starts(bytes, "ID3") && at(bytes, 3) < 0xff) {
        return audio;
    }
    // A bare MPEG frame: eleven sync bits, then version, layer, bitrate and
    // sample rate fields that all have a reserved value a real frame never uses.
    if (at(bytes, 0) !== 0xff || (at(bytes, 1) & 0xe0) !== 0xe0) {
        return null;
    }
    const version = (at(bytes, 1) >> 3) & 0x03;
    const layer = (at(bytes, 1) >> 1) & 0x03;
    const bitrate = (at(bytes, 2) >> 4) & 0x0f;
    const rate = (at(bytes, 2) >> 2) & 0x03;
    if (version === 1 || layer === 0 || bitrate === 0 || bitrate === 0x0f || rate === 3) {
        return null;
    }
    return audio;
}
