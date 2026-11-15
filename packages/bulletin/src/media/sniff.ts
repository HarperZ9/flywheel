/**
 * What these bytes actually are.
 *
 * The uploader's Content-Type is not consulted anywhere in this path. A sender
 * that labels a script `image/png` would otherwise pick the type the board later
 * serves it as, and serving a caller-chosen type off an origin that also serves
 * a read API is how a board becomes a hosting service for whatever anyone likes.
 * So the type is decided here, from the bytes, and the decision is what gets
 * stored and what gets sent back.
 *
 * SVG is refused despite being an image. It is XML, it can carry script, and a
 * browser rendering it inline runs that script on the board's origin. There is
 * no version of accepting it that is worth the drawings.
 */

import { BoardError } from "../errors.ts";
import {
    flac,
    gif,
    isoBmff,
    jpeg,
    mp3,
    ogg,
    png,
    riff,
    webm,
    type Format,
    type MediaKind,
} from "./formats.ts";

export type { Format, MediaKind };

/**
 * Order matters only where one signature could shadow another, and none of
 * these overlap. MP3 is last because its bare-frame form is the loosest test
 * here: eleven sync bits and four field checks, where every other format opens
 * with a string nothing else opens with.
 */
const RECOGNIZERS: ReadonlyArray<(bytes: Uint8Array) => Format | null> = [
    png,
    gif,
    jpeg,
    riff,
    isoBmff,
    webm,
    ogg,
    flac,
    mp3,
];

/** Every type the board will store, for the discovery document to publish. */
export const ACCEPTED_TYPES: readonly string[] = [
    "image/png",
    "image/gif",
    "image/jpeg",
    "image/webp",
    "image/avif",
    "audio/mpeg",
    "audio/ogg",
    "audio/flac",
    "audio/wav",
    "audio/mp4",
    "video/mp4",
    "video/webm",
];

/**
 * The smallest of the accepted containers still needs a header. Below this the
 * recognizers would be reading past the end of the buffer to decide, and a file
 * this short is a mistake rather than a picture.
 */
const MIN_BYTES = 32;

export function sniff(bytes: Uint8Array): Format {
    if (bytes.byteLength < MIN_BYTES) {
        throw new BoardError(
            415,
            "media_unsupported",
            "upload is too short to be a media file",
            `at least ${MIN_BYTES} bytes`,
        );
    }
    for (const recognize of RECOGNIZERS) {
        const format = recognize(bytes);
        if (format !== null) {
            return format;
        }
    }
    throw new BoardError(
        415,
        "media_unsupported",
        "the board does not recognise these bytes as a format it accepts",
        `send one of: ${ACCEPTED_TYPES.join(", ")}. SVG is refused because it can carry script.`,
        { accepted: ACCEPTED_TYPES },
    );
}
