import assert from "node:assert/strict";
import { test } from "node:test";

import { hasPlaceholderIds, parseJsonArray } from "../scripts/provision.mjs";

/**
 * The provisioning script reads two account ids out of wrangler and writes them
 * into a git-ignored config. Two things in it can be quietly wrong: the parse
 * that finds the id inside wrangler's output, and the guard that decides a
 * config is safe to overwrite. Both are tested here because both fail silently
 * in the direction that loses work.
 */

test("an id is read out of output that carries progress lines around it", () => {
    const noisy = [
        "\u2B24 Listing databases...",
        '[{"uuid":"a1b2","name":"bulletin","version":"production"}]',
        "Done.",
    ].join("\n");
    const rows = parseJsonArray(noisy);
    assert.equal(rows?.length, 1);
    assert.equal(rows?.[0].name, "bulletin");
    assert.equal(rows?.[0].uuid, "a1b2");
});

test("output with no array is null rather than an empty list", () => {
    // An empty list reads as "the account has no databases", which would send
    // the script on to create a second one.
    assert.equal(parseJsonArray("Not logged in."), null);
    assert.equal(parseJsonArray("["), null);
    assert.equal(parseJsonArray("{}"), null);
    assert.equal(parseJsonArray("[not json]"), null);
});

test("an empty account really is an empty list", () => {
    assert.deepEqual(parseJsonArray("[]"), []);
});

test("the unconfigured config is recognised as unconfigured", () => {
    assert.equal(hasPlaceholderIds('database_id = "REPLACE_WITH_D1_DATABASE_ID"'), true);
    // The dead sentinels are shaped like real ids on purpose. A guard that only
    // looked for REPLACE_WITH would read this board as configured and refuse to
    // write it, which is the case that actually exists on disk today.
    assert.equal(
        hasPlaceholderIds('database_id = "00000000-0000-4000-8000-000000000001"'),
        true,
    );
    assert.equal(hasPlaceholderIds('id = "0000000000000000000000000000dead"'), true);
});

test("a configured board is protected from being overwritten", () => {
    const real = [
        'database_id = "7f3a91c2-4d1e-4b8a-9c5f-2e6d8a0b1c3f"',
        'id = "9c1d4e7a2b5f80396c4d1a7b2e5f8031"',
    ].join("\n");
    assert.equal(hasPlaceholderIds(real), false);
});
