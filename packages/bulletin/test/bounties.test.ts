import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";
import { DatabaseSync } from "node:sqlite";

import { signRequest, makeSigner, type Signer } from "./helpers.ts";
import {
    insertBountyClaim,
    insertBountyReview,
    insertBountySubmission,
    nonceResult,
    releaseBountyClaim,
    spendNonce,
} from "../src/db.ts";
import worker, { type Env } from "../src/worker.ts";

const ROOT = new URL("../", import.meta.url);
const NOW = 1_800_000_000;
const ctx = { waitUntil: (promise: Promise<unknown>) => void promise.catch(() => {}), passThroughOnException: () => {} } as unknown as ExecutionContext;

test("signed bounty creation records a replay result and leaves ordinary posts independent", async () => {
    const world = await worldWithAgents("requester");
    const bountyRequest = await signedJson(world.requester, "/v1/bounties", bountyPayload({ claim_limit: 2 }), "create-bounty");

    const created = await call(world.env, bountyRequest);
    const replay = await call(world.env, await signedJson(world.requester, "/v1/bounties", bountyPayload({ claim_limit: 2 }), "create-bounty"));

    assert.equal(created.status, 201);
    assert.equal(created.body.bounty.payment.state, "payment_unverified");
    assert.equal(created.body.bounty.payment.verified_paid, null);
    assert.equal(created.body.bounty.payment.external_payment_state, "unknown");
    assert.equal("paid" in created.body.bounty.payment, false);
    assert.equal(replay.status, 409);
    assert.equal(replay.body.code, "nonce_reused");
    assert.deepEqual(replay.body.applied, { kind: "bounty", id: created.body.bounty.id });

    const post = await call(world.env, await signedJson(world.requester, "/v1/posts", { room: "agent-tooling", body: "ordinary posts still work" }, "ordinary-post"));
    assert.equal(post.status, 201);
    assert.equal(post.body.post.room, "agent-tooling");

    const bounties = await call(world.env, new Request("https://board.example/v1/bounties"));
    assert.equal(bounties.status, 200);
    assert.equal(bounties.body.bounties.length, 1);
});

test("MCP bounty tools call the same create and read core", async () => {
    const world = await worldWithAgents("requester");
    const created = await callRpc(world.env, await signedRpc(world.requester, "board_create_bounty", bountyPayload({ claim_limit: 2 }), "mcp-create"));

    assert.equal(created.result.isError, false);
    const bounty = created.result.structuredContent.bounty;
    assert.equal(bounty.payment.state, "payment_unverified");

    const read = await callRpc(world.env, rpcRequest("board_bounty", { id: bounty.id }));
    assert.equal(read.result.isError, false);
    assert.equal(read.result.structuredContent.bounty.id, bounty.id);
    assert.equal(read.result.structuredContent.bounty.terms.terms_hash, bounty.terms.terms_hash);
});

test("claim limit is enforced and old claims stay bound after terms revision", async () => {
    const world = await worldWithAgents("requester", "claimant-one", "claimant-two");
    const create = await createBountyHttp(world, bountyPayload({ claim_limit: 1, offer_amount_minor: 100 }));
    const bountyId = create.bounty.id as string;
    const termsHash = create.bounty.terms.terms_hash as string;

    const claim = await call(world.env, await signedJson(world.claimants[0]!, `/v1/bounties/${bountyId}/claims`, { terms_version: 1, terms_hash: termsHash }, "claim-one"));
    assert.equal(claim.status, 201);
    assert.equal(claim.body.claim.terms_version, 1);
    assert.equal(claim.body.claim.terms_hash, termsHash);

    const revised = await call(world.env, await signedJson(world.requester, `/v1/bounties/${bountyId}/terms`, bountyPayload({ claim_limit: 3, offer_amount_minor: 200 }), "revise-terms"));
    assert.equal(revised.status, 200);
    assert.equal(revised.body.active_claims_keep_original_terms, true);
    assert.equal(revised.body.bounty.current_terms_version, 2);

    const blocked = await call(world.env, await signedJson(world.claimants[1]!, `/v1/bounties/${bountyId}/claims`, { terms_version: 1, terms_hash: termsHash }, "claim-two"));
    assert.equal(blocked.status, 409);
    assert.equal(blocked.body.code, "capacity");

    const readback = await call(world.env, new Request(`https://board.example/v1/bounties/${bountyId}`));
    assert.equal(readback.body.bounty.current_terms_version, 2);
    assert.equal(readback.body.claims[0].terms_version, 1);
    assert.equal(readback.body.claims[0].terms_hash, termsHash);
});

test("evidence submission validates anchors, redacts secrets, and accepted review is not payment", async () => {
    const world = await worldWithAgents("requester", "claimant");
    const create = await createBountyHttp(world, bountyPayload({ claim_limit: 1 }));
    const bountyId = create.bounty.id as string;
    const termsHash = create.bounty.terms.terms_hash as string;
    const claimed = await call(world.env, await signedJson(world.claimants[0]!, `/v1/bounties/${bountyId}/claims`, { terms_version: 1, terms_hash: termsHash }, "claim"));
    const claimId = claimed.body.claim.id as string;

    const checked = await call(world.env, await signedJson(world.claimants[0]!, `/v1/bounty-claims/${claimId}/submissions`, {
        proof_text: "I checked the output.",
        source_anchors: [{ source: "receipt:1", source_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", line_range: { start: 1, end: 1 }, checked: true }],
    }, "checked-anchor"));
    assert.equal(checked.status, 400);
    assert.equal(checked.body.code, "bad_request");

    const secret = await call(world.env, await signedJson(world.claimants[0]!, `/v1/bounty-claims/${claimId}/submissions`, {
        proof_text: "api_key=sk-secretsecretsecret",
        source_anchors: [{ source: "receipt:1", source_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", line_range: { start: 1, end: 1 } }],
    }, "secret-proof"));
    assert.equal(secret.status, 400);
    assert.equal(secret.body.code, "bad_request");

    const secretMissingNote = await call(world.env, await signedJson(world.claimants[0]!, `/v1/bounty-claims/${claimId}/submissions`, {
        proof_text: "The public proof omits one source.",
        source_anchors: [{ source: "private-log", missing: true, note: "api_key=sk-secretsecretsecret" }],
    }, "secret-missing-note"));
    assert.equal(secretMissingNote.status, 400);
    assert.equal(secretMissingNote.body.code, "bad_request");

    const secretRedactionNote = await call(world.env, await signedJson(world.claimants[0]!, `/v1/bounty-claims/${claimId}/submissions`, {
        proof_text: "The JSON value is redacted.",
        source_anchors: [{ source: "result-json", source_hash: "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", json_pointer: "/secret", source_value: "[redacted]", redacted: true, note: "password=hunter2" }],
    }, "secret-redaction-note"));
    assert.equal(secretRedactionNote.status, 400);
    assert.equal(secretRedactionNote.body.code, "bad_request");

    const unusedLineSourceValue = await call(world.env, await signedJson(world.claimants[0]!, `/v1/bounty-claims/${claimId}/submissions`, {
        proof_text: "A line range cannot carry a source value that the board would drop.",
        source_anchors: [{ source: "receipt:1", source_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", line_range: { start: 1, end: 1 }, source_value: "api_key=sk-secretsecretsecret" }],
    }, "unused-line-source-value"));
    assert.equal(unusedLineSourceValue.status, 400);
    assert.equal(unusedLineSourceValue.body.code, "bad_request");

    const redactedCharRange = await call(world.env, await signedJson(world.claimants[0]!, `/v1/bounty-claims/${claimId}/submissions`, {
        proof_text: "A character range cannot claim redaction semantics.",
        source_anchors: [{ source: "receipt:1", source_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", char_range: { start: 0, end: 10 }, redacted: true, note: "Sensitive value omitted." }],
    }, "redacted-char-range"));
    assert.equal(redactedCharRange.status, 400);
    assert.equal(redactedCharRange.body.code, "bad_request");

    const submitted = await call(world.env, await signedJson(world.claimants[0]!, `/v1/bounty-claims/${claimId}/submissions`, {
        proof_text: "The evidence is in the linked receipt.",
        source_anchors: [
            { source: "receipt:1", source_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", line_range: { start: 1, end: 4 } },
            { source: "private-log", missing: true, note: "Local trace omitted from the public board." },
            { source: "result-json", source_hash: "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", json_pointer: "/secret", source_value: "[redacted]", redacted: true, note: "Credential value removed." },
        ],
    }, "submit-proof"));
    assert.equal(submitted.status, 201);
    assert.equal(submitted.body.source_anchors_checked_by_board, false);
    assert.equal(submitted.body.no_fetch_performed, true);
    const submissionId = submitted.body.submission.id as string;

    const wrongReviewer = await call(world.env, await signedJson(world.claimants[0]!, `/v1/bounty-submissions/${submissionId}/reviews`, { decision: "accepted", review_note: "Looks good." }, "wrong-reviewer"));
    assert.equal(wrongReviewer.status, 403);
    assert.equal(wrongReviewer.body.code, "account_mismatch");

    const accepted = await call(world.env, await signedJson(world.requester, `/v1/bounty-submissions/${submissionId}/reviews`, { decision: "accepted", review_note: "Matches the criteria." }, "requester-review"));
    assert.equal(accepted.status, 200);
    assert.equal(accepted.body.accepted, true);
    assert.equal(accepted.body.verified_paid, null);
    assert.equal(accepted.body.external_payment_state, "unknown");
    assert.equal("paid" in accepted.body, false);
    assert.equal(accepted.body.payment_state, "payment_unverified");
    assert.equal(accepted.body.review.establishes_payment, false);
    assert.equal(accepted.body.review.verified_paid, null);
    assert.equal(accepted.body.review.external_payment_state, "unknown");
    assert.equal("paid" in accepted.body.review, false);

    const readback = await call(world.env, new Request(`https://board.example/v1/bounty-submissions/${submissionId}`));
    assert.equal(readback.body.content_is_untrusted, true);
    assert.equal(typeof readback.body.notice, "string");
    assert.equal(readback.body.submission.status, "accepted");
    assert.equal(readback.body.submission.review.verified_paid, null);
    assert.equal(readback.body.submission.review.external_payment_state, "unknown");
    assert.equal(readback.body.submission.review.content_is_untrusted, true);
    assert.equal("paid" in readback.body.submission.review, false);

    const termsRead = await call(world.env, new Request(`https://board.example/v1/bounties/${bountyId}/terms/1`));
    assert.equal(termsRead.body.content_is_untrusted, true);
    assert.equal(typeof termsRead.body.notice, "string");
    assert.equal(termsRead.body.terms.content_is_untrusted, true);

    const claimRead = await call(world.env, new Request(`https://board.example/v1/bounty-claims/${claimId}`));
    assert.equal(claimRead.body.content_is_untrusted, true);
    assert.equal(typeof claimRead.body.notice, "string");
    assert.equal(claimRead.body.claim.content_is_untrusted, true);
});

test("MCP revise bounty terms schema matches HTTP by keeping room optional", async () => {
    const world = await worldWithAgents("requester");
    const listed = await callRpc(world.env, rpcEnvelopeRequest("tools/list", {}));
    const tool = listed.result.tools.find((item: Record<string, any>) => item.name === "board_revise_bounty_terms");

    assert.ok(tool);
    assert.equal(tool.inputSchema.required.includes("bounty_id"), true);
    assert.equal(tool.inputSchema.required.includes("room"), false);
});

test("stale guarded bounty writes clear pending nonces and replay never reports missing applied rows", async () => {
    const world = await worldWithAgents("requester", "claimant-one", "claimant-two");
    const create = await createBountyHttp(world, bountyPayload({ claim_limit: 1 }));
    const bountyId = create.bounty.id as string;
    const termsHash = create.bounty.terms.terms_hash as string;
    const claim = await call(world.env, await signedJson(world.claimants[0]!, `/v1/bounties/${bountyId}/claims`, { terms_version: 1, terms_hash: termsHash }, "claim-for-races"));
    const claimId = claim.body.claim.id as string;

    const submit = await call(world.env, await signedJson(world.claimants[0]!, `/v1/bounty-claims/${claimId}/submissions`, {
        proof_text: "The evidence is in the linked receipt.",
        source_anchors: [{ source: "receipt:1", source_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", line_range: { start: 1, end: 1 } }],
    }, "submit-for-races"));
    const submissionId = submit.body.submission.id as string;

    const review = await call(world.env, await signedJson(world.requester, `/v1/bounty-submissions/${submissionId}/reviews`, { decision: "accepted", review_note: "Accepted for stale-write setup." }, "initial-review"));
    assert.equal(review.status, 200);

    const staleReviewNonce = await spendFor(world, world.requester, "stale-review");
    await assert.rejects(
        insertBountyReview(world.env.DB, {
            id: "review-that-does-not-exist",
            submissionId,
            reviewer: world.requester.thumbprint,
            createdAt: NOW,
            decision: "accepted",
            reviewNote: "This lost a race.",
            nonceKey: staleReviewNonce,
        }),
        /bounty review did not allocate an id/,
    );

    const staleSubmitNonce = await spendFor(world, world.claimants[0]!, "stale-submit");
    await assert.rejects(
        insertBountySubmission(world.env.DB, {
            id: "submission-that-does-not-exist",
            claimId,
            submissionVersion: 2,
            submitter: world.claimants[0]!.thumbprint,
            createdAt: NOW,
            proofText: "This lost a race.",
            sourceAnchorsJson: "[]",
            sourceAnchorCount: 1,
            nonceKey: staleSubmitNonce,
        }),
        /bounty submission did not allocate an id/,
    );

    const staleReleaseNonce = await spendFor(world, world.claimants[0]!, "stale-release");
    assert.equal(await releaseBountyClaim(world.env.DB, claimId, world.claimants[0]!.thumbprint, NOW, staleReleaseNonce), false);

    const capacityCreate = await createBountyHttp(world, bountyPayload({ title: "Capacity race fixture", claim_limit: 1 }));
    const capacityBountyId = capacityCreate.bounty.id as string;
    const capacityTermsHash = capacityCreate.bounty.terms.terms_hash as string;
    const activeClaim = await call(world.env, await signedJson(world.claimants[0]!, `/v1/bounties/${capacityBountyId}/claims`, { terms_version: 1, terms_hash: capacityTermsHash }, "capacity-existing-claim"));
    assert.equal(activeClaim.status, 201);

    const capacityNonce = await spendFor(world, world.claimants[1]!, "capacity-claim");
    await assert.rejects(
        insertBountyClaim(world.env.DB, {
            id: "claim-that-does-not-exist",
            bountyId: capacityBountyId,
            termsVersion: 1,
            termsHash: capacityTermsHash,
            claimant: world.claimants[1]!.thumbprint,
            createdAt: NOW,
            claimNote: null,
            nonceKey: capacityNonce,
        }),
        /bounty claim did not allocate an id/,
    );

    assertNonceHasNoResult(await nonceResult(world.env.DB, staleReviewNonce));
    assertNonceHasNoResult(await nonceResult(world.env.DB, staleSubmitNonce));
    assertNonceHasNoResult(await nonceResult(world.env.DB, staleReleaseNonce));
    assertNonceHasNoResult(await nonceResult(world.env.DB, capacityNonce));

    const replay = await call(world.env, await signedJson(world.requester, `/v1/bounty-submissions/${submissionId}/reviews`, { decision: "accepted", review_note: "Retry after stale DB loser." }, "stale-review"));
    assert.equal(replay.status, 409);
    assert.equal(replay.body.code, "nonce_reused");
    assert.equal(replay.body.applied, undefined);
});

async function createBountyHttp(world: World, payload: Record<string, unknown>): Promise<Record<string, any>> {
    const response = await call(world.env, await signedJson(world.requester, "/v1/bounties", payload, `create-${Math.random()}`));
    assert.equal(response.status, 201);
    return response.body;
}

function bountyPayload(overrides: Record<string, unknown> = {}): Record<string, unknown> {
    return {
        room: "agent-tooling",
        title: "Reproduce the failing case",
        summary: "Show the smallest failing request.",
        body: "Run the bounded check and report the exact source anchor.",
        acceptance_criteria: "The review accepts a concise proof with source anchors.",
        offer_amount_minor: 100,
        offer_currency: "USD",
        deadline_at: NOW + 86_400,
        claim_limit: 1,
        ...overrides,
    };
}

interface World {
    db: SqliteD1;
    env: Env;
    requester: Signer;
    claimants: Signer[];
}

async function worldWithAgents(requesterHandle: string, ...claimantHandles: string[]): Promise<World> {
    const db = new SqliteD1();
    applySchema(db.sqlite);
    seedRoom(db.sqlite);
    const requester = await makeSigner();
    seedAgent(db.sqlite, requester, requesterHandle);
    const claimants = [];
    for (const handle of claimantHandles) {
        const signer = await makeSigner();
        seedAgent(db.sqlite, signer, handle);
        claimants.push(signer);
    }
    return { db, env: envWith(db), requester, claimants };
}

function envWith(db: SqliteD1): Env {
    return {
        DB: db as unknown as D1Database,
        KEYS: {} as KVNamespace,
        FEED: {
            idFromName: () => "global",
            get: () => ({ fetch: async () => new Response(null, { status: 204 }) }),
        } as unknown as DurableObjectNamespace,
        BULLETIN_POW_BITS: 20,
        BULLETIN_SIGNATURE_MAX_AGE: 300,
        BULLETIN_EMBED_ORIGIN: "https://harperz9.github.io",
    };
}

async function signedJson(signer: Signer, path: string, payload: unknown, nonce: string): Promise<Request> {
    return signRequest(signer, {
        method: "POST",
        url: `https://board.example${path}`,
        body: JSON.stringify(payload),
        nonce,
    });
}

async function spendFor(world: World, signer: Signer, nonce: string): Promise<string> {
    const key = `${signer.thumbprint}:${nonce}`;
    assert.equal(await spendNonce(world.env.DB, key, NOW + 300), true);
    return key;
}

function assertNonceHasNoResult(row: { result_kind: string | null; result_id: string | null } | null): void {
    assert.ok(row);
    assert.equal(row.result_kind, null);
    assert.equal(row.result_id, null);
}

async function signedRpc(signer: Signer, name: string, args: unknown, nonce: string): Promise<Request> {
    return signRequest(signer, {
        method: "POST",
        url: "https://board.example/mcp",
        body: JSON.stringify(rpcEnvelope(name, args)),
        nonce,
    });
}

function rpcRequest(name: string, args: unknown): Request {
    return new Request("https://board.example/mcp", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(rpcEnvelope(name, args)),
    });
}

function rpcEnvelopeRequest(method: string, params: unknown): Request {
    return new Request("https://board.example/mcp", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
    });
}

function rpcEnvelope(name: string, args: unknown): Record<string, unknown> {
    return { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } };
}

async function callRpc(env: Env, request: Request): Promise<Record<string, any>> {
    const response = await worker.fetch(request, env, ctx);
    assert.equal(response.status, 200);
    return response.json() as Promise<Record<string, any>>;
}

async function call(env: Env, request: Request): Promise<{ status: number; body: Record<string, any> }> {
    const response = await worker.fetch(request, env, ctx);
    return { status: response.status, body: await response.json() as Record<string, any> };
}

function applySchema(db: DatabaseSync): void {
    for (const name of readdirSync(new URL("../schema/", import.meta.url)).filter((item) => item.endsWith(".sql")).sort()) {
        db.exec(readFileSync(new URL(`../schema/${name}`, import.meta.url), "utf-8"));
    }
}

function seedRoom(db: DatabaseSync): void {
    db.prepare("INSERT INTO rooms (slug, title, purpose, created_at, created_by, locked, post_count) VALUES (?, ?, ?, ?, ?, 0, 0)")
        .run("agent-tooling", "Agent tooling", "Work on agent tooling", NOW, "operator");
}

function seedAgent(db: DatabaseSync, signer: Signer, handle: string): void {
    db.prepare(
        `INSERT INTO agents (thumbprint, handle, public_jwk, operator_host, tier, first_seen, last_seen, post_count, flags_received, suspended_at)
         VALUES (?, ?, ?, NULL, 'verified', ?, ?, 0, 0, NULL)`,
    ).run(signer.thumbprint, handle, JSON.stringify(signer.jwk), NOW, NOW);
}

class SqliteD1 {
    readonly sqlite = new DatabaseSync(":memory:");

    prepare(sql: string): D1PreparedStatement {
        return new SqliteStatement(this.sqlite, sql) as unknown as D1PreparedStatement;
    }

    async batch(statements: D1PreparedStatement[]): Promise<D1Result[]> {
        const out: D1Result[] = [];
        this.sqlite.exec("BEGIN IMMEDIATE");
        try {
            for (const statement of statements as unknown as SqliteStatement[]) {
                out.push(statement.execute() as unknown as D1Result);
            }
            this.sqlite.exec("COMMIT");
        } catch (error) {
            this.sqlite.exec("ROLLBACK");
            throw error;
        }
        return out;
    }
}

class SqliteStatement {
    private args: unknown[] = [];
    private readonly db: DatabaseSync;
    private readonly sql: string;

    constructor(db: DatabaseSync, sql: string) {
        this.db = db;
        this.sql = sql;
    }

    bind(...args: unknown[]): this {
        this.args = args;
        return this;
    }

    async all<T>(): Promise<{ results: T[] }> {
        return { results: this.selectAll<T>() };
    }

    async first<T>(): Promise<T | null> {
        return this.selectFirst<T>();
    }

    async run(): Promise<{ meta: { changes: number } }> {
        return this.runChange();
    }

    execute(): { results?: unknown[]; meta: { changes: number } } {
        if (/^\s*SELECT\b/i.test(this.sql)) {
            return { results: this.selectAll<unknown>(), meta: { changes: 0 } };
        }
        return this.runChange();
    }

    private selectAll<T>(): T[] {
        return this.db.prepare(this.sql).all(...this.args as any[]) as T[];
    }

    private selectFirst<T>(): T | null {
        return (this.db.prepare(this.sql).get(...this.args as any[]) ?? null) as T | null;
    }

    private runChange(): { meta: { changes: number } } {
        const result = this.db.prepare(this.sql).run(...this.args as any[]);
        return { meta: { changes: Number(result.changes ?? 0) } };
    }
}
