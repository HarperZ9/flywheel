/**
 * The two attachment routes.
 *
 * They are described apart from the rest because the upload is the one request
 * on this board whose body is not JSON. The body is the file, so the
 * content-digest the signature covers is a digest of the bytes that end up
 * stored, and nothing about the upload rides in an unsigned header.
 */

import { MAX_ALT_LENGTH, MAX_MEDIA_BYTES, mediaEnabled, type Env } from "../config.ts";
import { ACCEPTED_TYPES } from "../media/sniff.ts";
import { path, problemResponse, SIGNED, type Obj } from "./shapes.ts";

export function mediaPaths(env: Env): Obj {
    const enabled = mediaEnabled(env);
    return {
        "/v1/media": {
            post: {
                tags: ["write"],
                summary: "Upload a picture, sound, or clip",
                description: uploadDescription(enabled),
                operationId: "uploadMedia",
                security: SIGNED,
                requestBody: {
                    required: true,
                    description: `The file itself, at most ${MAX_MEDIA_BYTES} bytes and less on lower tiers.`,
                    content: {
                        "application/octet-stream": { schema: { type: "string", format: "binary" } },
                    },
                },
                responses: {
                    "201": {
                        description: "The stored media. Already held bytes answer 201 with deduplicated: true.",
                        content: { "application/json": { schema: { type: "object" } } },
                    },
                    "401": problemResponse(),
                    "403": problemResponse(),
                    "413": problemResponse(),
                    "415": problemResponse(),
                    "429": problemResponse(),
                    "503": problemResponse(),
                },
            },
        },
        "/v1/media/{id}": {
            get: {
                tags: ["read"],
                summary: "Fetch stored media",
                description:
                    "Open and unauthenticated: a picture in a public post is as public as the post. " +
                    "The content type is the one the board read from the bytes, never one an uploader " +
                    "declared. Range requests are answered, which is what a browser needs to play sound " +
                    "or video. The id is a hash of the body, so the response is cached for a year.",
                operationId: "getMedia",
                parameters: [path("id", "base64url SHA-256 of the bytes, unpadded")],
                responses: {
                    "200": { description: "The file", content: { "application/octet-stream": { schema: { type: "string", format: "binary" } } } },
                    "206": { description: "The requested byte range" },
                    "404": problemResponse(),
                    "416": problemResponse(),
                    "451": problemResponse(),
                    "503": problemResponse(),
                },
            },
        },
    };
}

/**
 * The document says whether this deployment can store anything, because the
 * same code runs on a board with no bucket bound. Publishing a route that
 * always refuses, without saying so, is worse than publishing no route.
 */
function uploadDescription(enabled: boolean): string {
    const how =
        `Accepted: ${ACCEPTED_TYPES.join(", ")}. The board decides the type by reading the bytes and ` +
        "refuses a file that is not the format it opens as. The answer carries an id, which is the " +
        "base64url SHA-256 of what was stored. Attach it to a post with attachments: [{ media_id, alt }], " +
        `where alt is required and at most ${MAX_ALT_LENGTH} characters.`;
    if (enabled) {
        return how;
    }
    return `This deployment has no media store, so every upload answers 503 media_disabled and retrying will not change that. ${how}`;
}
