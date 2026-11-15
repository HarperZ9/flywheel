/**
 * Things a deploy can get wrong that no other test here would notice.
 *
 * The first is the migration list. `db:local` and `db:remote` are two hand
 * written strings naming the same schema files, and the remote one was missing
 * `0005_rotation.sql` while the code that needs it was already merged. That
 * migration adds columns to `agents` rather than creating a table of its own,
 * so a board brought up from the remote list would have had every table anyone
 * looked for and failed every rotation request on a column that is not there.
 *
 * That is also why the doctor's expectations are checked against the schema
 * directory below. A census of table names cannot see a migration that adds no
 * table, and the table list itself had gone stale at nine while the schema grew
 * to twelve, so a board with no media tables reported itself ready to serve.
 *
 * The second is the version. Four feature pull requests landed on top of 0.2.0
 * without moving it, so the contract reported the same number for a board that
 * carries media and a board that has never heard of it. A client caching by
 * version has no way to tell those apart. The fix is not a rule that says to
 * remember; it is a pin over the surface the board advertises, which fails the
 * moment a route, a tool, or an operation is added or removed.
 *
 * Neither test reaches the network. Both read the same modules the worker
 * serves from.
 */

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { SERVICE_VERSION, type Env } from "../src/config.ts";
import { discoveryDocument } from "../src/discovery.ts";
import { openApiDocument } from "../src/openapi.ts";
import { listTools } from "../src/tools.ts";
import { EXPECTED_AGENT_COLUMNS, EXPECTED_TABLES } from "../src/tools/health.ts";

const ROOT = new URL("../", import.meta.url);

/**
 * The advertised surface, pinned. Bump SERVICE_VERSION and re-pin whenever a
 * route, an MCP tool, or an OpenAPI operation is added, renamed, or dropped.
 */
const REVIEWED_SURFACE_SHA256 =
    "14f6cad9bcc914517c56b6f7e1a6d17e866a3bed73d3c620a256c1323d126cc6";

/** Media is an optional binding, so the surface differs by deployment. Both are covered. */
const WITHOUT_MEDIA = { BULLETIN_POW_BITS: 20, BULLETIN_SIGNATURE_MAX_AGE: 300 } as unknown as Env;
const WITH_MEDIA = { ...WITHOUT_MEDIA, MEDIA: {} } as unknown as Env;

function schemaFilesFrom(script: string): string[] {
    const names: string[] = [];
    for (const match of script.matchAll(/schema\/([0-9]+_[a-z0-9_]+\.sql)/g)) {
        if (match[1]) names.push(match[1]);
    }
    return names;
}

function surfaceRecords(env: Env, label: string): string[] {
    const url = new URL("https://board.example/");
    const contract = discoveryDocument(url, env) as Record<string, unknown>;
    const endpoints = contract.endpoints as Record<string, string>;
    const media = contract.media as { enabled: boolean };
    const openapi = openApiDocument(url, env) as { paths: Record<string, Record<string, unknown>> };
    const records = [
        // The media routes are advertised whether or not a bucket is bound, so
        // their names cannot tell a caller that uploads work. The enabled flag
        // is the one honest signal, and leaving it out of the pin would let a
        // bucketless board and a working one hash the same.
        `${label}\tmedia_enabled\t${media.enabled}`,
        ...Object.keys(endpoints).map((name) => `${label}\tendpoint\t${name}`),
        ...listTools().map((tool) => `${label}\ttool\t${tool.name}`),
    ];
    for (const [path, operations] of Object.entries(openapi.paths)) {
        for (const method of Object.keys(operations)) {
            records.push(`${label}\toperation\t${method.toUpperCase()} ${path}`);
        }
    }
    return records.sort();
}

function surfaceFingerprint(): string {
    const records = [
        ...surfaceRecords(WITHOUT_MEDIA, "base"),
        ...surfaceRecords(WITH_MEDIA, "media"),
    ];
    return createHash("sha256").update(records.join("\n") + "\n").digest("hex");
}

test("both migration lists apply every schema file, in order", () => {
    const pkg = JSON.parse(readFileSync(new URL("package.json", ROOT), "utf-8"));
    const onDisk = readdirSync(new URL("schema/", ROOT))
        .filter((name) => name.endsWith(".sql"))
        .sort();
    assert.ok(onDisk.length > 0, "no schema files were found to check against");
    for (const script of ["db:local", "db:remote"]) {
        assert.deepEqual(
            schemaFilesFrom(pkg.scripts[script]),
            onDisk,
            `${script} does not apply every schema file in order`,
        );
    }
});

test("the advertised surface still hashes to the reviewed pin", () => {
    // What fails here is a surface change that went out under an unchanged
    // version. Re-pinning without bumping SERVICE_VERSION defeats the point.
    assert.equal(
        surfaceFingerprint(),
        REVIEWED_SURFACE_SHA256,
        `the advertised surface moved while the version reads ${SERVICE_VERSION}; `
            + "bump SERVICE_VERSION and package.json, then re-pin REVIEWED_SURFACE_SHA256",
    );
});

/** Every schema file, concatenated, so a statement is found wherever it lives. */
function allSchemaSql(): string {
    return readdirSync(new URL("schema/", ROOT))
        .filter((name) => name.endsWith(".sql"))
        .sort()
        .map((name) => readFileSync(new URL(`schema/${name}`, ROOT), "utf-8"))
        .join("\n");
}

test("the doctor looks for every table the schema creates", () => {
    // The doctor cannot read the filesystem at runtime, so its list is written
    // by hand and drifts silently. It had drifted: nine names against twelve
    // tables, which made a board with no media storage report itself ready.
    const sql = allSchemaSql();
    const created = [
        ...sql.matchAll(/CREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_]+)/gi),
    ]
        .map((match) => match[1])
        .filter((name): name is string => Boolean(name));
    assert.ok(created.length > 0, "no CREATE TABLE statement was found to check against");
    assert.deepEqual(
        [...EXPECTED_TABLES].sort(),
        [...new Set(created)].sort(),
        "bulletin_doctor's table list does not match the tables schema/ creates",
    );
});

test("the doctor looks for every column a migration adds to agents", () => {
    // A migration that adds no table is invisible to a table census, which is
    // how the rotation columns could have been missing on a board the doctor
    // called ready.
    const added = [
        ...allSchemaSql().matchAll(/ALTER\s+TABLE\s+agents\s+ADD\s+COLUMN\s+([a-z_]+)/gi),
    ]
        .map((match) => match[1])
        .filter((name): name is string => Boolean(name));
    assert.ok(added.length > 0, "no ALTER TABLE agents statement was found to check against");
    assert.deepEqual(
        [...EXPECTED_AGENT_COLUMNS].sort(),
        [...new Set(added)].sort(),
        "bulletin_doctor's agents column list does not match what the migrations add",
    );
});

test("the pin covers whether media is on, not only that the route is listed", () => {
    // A false-success control, and the first run of it earned its place: the
    // fingerprint originally folded route names alone, and the two deployments
    // hashed identically because the routes are published either way. A pin
    // that cannot separate a board accepting uploads from one refusing them
    // would go green on exactly the deploy this file exists to catch.
    const base = surfaceRecords(WITHOUT_MEDIA, "x");
    const withMedia = surfaceRecords(WITH_MEDIA, "x");
    assert.notDeepEqual(base, withMedia, "the fingerprint cannot see the media binding");
    assert.ok(base.includes("x\tmedia_enabled\tfalse"), "a board with no bucket reports media on");
    assert.ok(withMedia.includes("x\tmedia_enabled\ttrue"), "a board with a bucket reports media off");
    assert.ok(
        withMedia.some((record) => record.includes("/v1/media")),
        "no media operation reached the fingerprint",
    );
});
