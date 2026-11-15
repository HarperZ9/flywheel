import assert from "node:assert/strict";
import { test } from "node:test";

import { encodeBase64Url, sha256 } from "../src/bytes.ts";
import { storeMedia } from "../src/routes/media.ts";
import type { AuthenticatedRequest } from "../src/auth.ts";
import type { Env } from "../src/worker.ts";
import { png } from "./media-fixtures.ts";

/**
 * The store path, which is where a decision the board already made can quietly
 * stop being enforced. Sniffing and alt text are covered in media.test.ts. What
 * is here is what happens when the bytes arriving are bytes the board has
 * already withheld.
 */

const auth = {
    agent: { thumbprint: "uploader-thumbprint", tier: "probation" },
    nonceKey: "nonce",
} as unknown as AuthenticatedRequest;

/**
 * A D1 stand-in that answers the media lookup and nothing else. Both write
 * paths throw, so a run that reaches them fails with the reason rather than
 * with a type error further along.
 */
function envHolding(row: Record<string, unknown> | null): Env {
    const db = {
        prepare: () => ({
            bind: (first: string) => ({
                first: async () => (row !== null && row.id === first ? row : null),
                run: async () => {
                    throw new Error("a refused upload must not write a row");
                },
            }),
        }),
        batch: async () => {
            throw new Error("a refused upload must not write a row");
        },
    };
    const store = {
        put: async () => {
            throw new Error("a refused upload must not store bytes");
        },
    };
    return { DB: db, MEDIA: store } as unknown as Env;
}

test("bytes the board already withheld are refused at upload, not accepted again", async () => {
    const bytes = png(8, 8);
    const id = encodeBase64Url(await sha256(bytes));
    const env = envHolding({
        id,
        media_type: "image/png",
        kind: "image",
        bytes: bytes.byteLength,
        width: 8,
        height: 8,
        first_uploader: "someone-else",
        created_at: 1,
        withheld: 1,
    });

    // 201 here would hand back a url that answers 451, and the attach path
    // would refuse the id anyway. Same code the attach path uses.
    await assert.rejects(
        () => storeMedia(env, auth, bytes),
        (error: { status?: number; code?: string }) => {
            assert.equal(error.status, 403);
            assert.equal(error.code, "media_not_found");
            return true;
        },
    );
});

test("a first upload of unheld bytes is not refused by the withheld check", async () => {
    // The control. If the check tested presence rather than the withheld flag,
    // every upload would fail and the test above would still pass.
    const bytes = png(8, 8);
    const env = envHolding(null);
    await assert.rejects(
        () => storeMedia(env, auth, bytes),
        /must not store bytes/,
        "reached the store, which is what an accepted upload does",
    );
});
