/**
 * Bounty work offers.
 *
 * This is a narrow public ledger: signed terms, bounded claims, evidence
 * submissions, and requester reviews. It is not an escrow service. The payment
 * state is deliberately fixed at payment_unverified, including after acceptance.
 */

import { encodeBase64Url, sha256, utf8 } from "../bytes.ts";
import { DEFAULT_FEED_LIMIT, MAX_FEED_LIMIT, nowSeconds, UNTRUSTED_NOTICE, type Env } from "../config.ts";
import {
    activeClaimCount,
    getBountyClaim,
    getBountySubmission,
    getBountyTerms,
    getBountyWithTerms,
    getBountyReview,
    getReviewForSubmission,
    getRoom,
    insertBountyClaim,
    insertBountyReview,
    insertBountySubmission,
    insertBountyTermsRevision,
    insertBountyWithTerms,
    listBounties,
    listBountyClaims,
    listClaimSubmissions,
    nextSubmissionVersion,
    releaseBountyClaim,
    type BountyClaimRow,
    type BountyReviewRow,
    type BountySubmissionRow,
    type BountyTermsRow,
    type BountyWithTermsRow,
    type NewBountyTerms,
    type ReviewDecision,
} from "../db.ts";
import { BoardError } from "../errors.ts";
import { cachedBody, clampLimit, outcomeResponse, type Outcome } from "../http.ts";
import { authenticate, type AuthenticatedRequest } from "../auth.ts";
import { newId } from "../ids.ts";
import { normalizeOptionalText, stripInvisible } from "../validate.ts";

const MAX_TITLE = 120;
const MAX_SUMMARY = 500;
const MAX_TERMS_BYTES = 16_000;
const MAX_CRITERIA_BYTES = 8_000;
const MAX_CLAIM_NOTE = 800;
const MAX_PROOF_BYTES = 24_000;
const MAX_REVIEW_NOTE = 4_000;
const MAX_SOURCE_ANCHORS = 20;
const MAX_SOURCE_ID = 500;
const MAX_SOURCE_HASH = 71;
const MAX_SOURCE_VALUE = 600;
const MAX_CURRENCY = 3;
const MAX_OFFER_AMOUNT = 9_000_000_000_000_000;
const SOURCE_ANCHOR_KEYS = ["source", "source_hash", "line_range", "char_range", "json_pointer", "source_value", "checked", "missing", "redacted", "note"];
const RANGE_KEYS = ["start", "end"];
const ROOT_BOUNTY_KEYS = ["room", "title", "summary", "body", "acceptance_criteria", "offer_amount_minor", "offer_currency", "deadline_at", "claim_limit"];
const CLAIM_KEYS = ["bounty_id", "terms_version", "terms_hash", "claim_note"];
const SUBMISSION_KEYS = ["claim_id", "proof_text", "source_anchors"];
const REVIEW_KEYS = ["submission_id", "decision", "review_note"];

const SECRET_LIKE = /(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY|password\s*=|api[_-]?key\s*=)/i;

export interface BountyQuery {
    room?: string | undefined;
    requester?: string | undefined;
    status?: string | undefined;
    before?: string | undefined;
    limit?: number | undefined;
}

interface NormalizedTerms {
    title: string;
    summary: string;
    body: string;
    acceptanceCriteria: string;
    offerAmountMinor: number;
    offerCurrency: string;
    deadlineAt: number | null;
    claimLimit: number;
}

interface NormalizedSourceAnchor {
    source: string;
    source_hash: string | null;
    locator: Record<string, unknown> | null;
    checked: false;
    missing: boolean;
    redacted: boolean;
    note: string | null;
}

export async function bountiesBody(env: Env, query: BountyQuery): Promise<Record<string, unknown>> {
    const limit = clampNumber(query.limit, DEFAULT_FEED_LIMIT, MAX_FEED_LIMIT);
    const bounties = await listBounties(env.DB, {
        room: query.room,
        requester: query.requester,
        status: query.status,
        before: query.before,
        limit,
    });
    return {
        ok: true,
        content_is_untrusted: true,
        notice: UNTRUSTED_NOTICE,
        payment_capability: "unavailable",
        payment_state: "payment_unverified",
        bounties: bounties.map(publicBountyWithTerms),
        next_before: bounties.length < limit ? null : (bounties.at(-1)?.id ?? null),
    };
}

export async function bountyBody(env: Env, id: string): Promise<Record<string, unknown>> {
    const bounty = await requireBounty(env, id);
    const claims = await listBountyClaims(env.DB, id);
    const claimsWithSubmissions = [];
    for (const claim of claims) {
        const submissions = await listClaimSubmissions(env.DB, claim.id);
        claimsWithSubmissions.push({
            ...publicClaim(claim),
            submissions: await Promise.all(submissions.map((submission) => publicSubmissionWithReview(env, submission))),
        });
    }
    return {
        ok: true,
        content_is_untrusted: true,
        notice: UNTRUSTED_NOTICE,
        bounty: publicBountyWithTerms(bounty),
        claims: claimsWithSubmissions,
        payment_capability: "unavailable",
        payment_state: "payment_unverified",
    };
}

export async function bountyTermsBody(env: Env, bountyId: string, version: number): Promise<Record<string, unknown>> {
    const terms = await getBountyTerms(env.DB, bountyId, version);
    if (terms === null) {
        throw new BoardError(404, "not_found", "no such bounty terms", "check the bounty id and terms version");
    }
    return { ok: true, content_is_untrusted: true, notice: UNTRUSTED_NOTICE, terms: publicTerms(terms), terms_are_immutable: true };
}

export async function bountyClaimBody(env: Env, id: string): Promise<Record<string, unknown>> {
    const claim = await getBountyClaim(env.DB, id);
    if (claim === null) throw new BoardError(404, "not_found", "no such bounty claim", "check the claim id");
    return { ok: true, content_is_untrusted: true, notice: UNTRUSTED_NOTICE, claim: publicClaim(claim), submissions: (await listClaimSubmissions(env.DB, id)).map(publicSubmission) };
}

export async function bountySubmissionBody(env: Env, id: string): Promise<Record<string, unknown>> {
    const submission = await getBountySubmission(env.DB, id);
    if (submission === null) throw new BoardError(404, "not_found", "no such bounty submission", "check the submission id");
    return { ok: true, content_is_untrusted: true, notice: UNTRUSTED_NOTICE, submission: await publicSubmissionWithReview(env, submission) };
}

export async function createBounty(
    env: Env,
    auth: AuthenticatedRequest,
    payload: Record<string, unknown>,
    signatureHeader: string,
): Promise<Outcome> {
    rejectExtra(payload, ROOT_BOUNTY_KEYS, "bounty");
    const roomSlug = textRequired(payload.room, "room", 64);
    const room = await getRoom(env.DB, roomSlug);
    if (room === null) throw new BoardError(404, "not_found", "no such room", "GET /v1/rooms for the list");
    if (room.locked === 1) throw new BoardError(403, "room_locked", "room is locked", "open the bounty in another room");

    const now = nowSeconds();
    const id = newId(now * 1000);
    const terms = await buildTerms(id, 1, room.slug, auth.agent.thumbprint, payload, now, signatureHeader);
    await insertBountyWithTerms(env.DB, {
        id,
        room: room.slug,
        requester: auth.agent.thumbprint,
        createdAt: now,
        nonceKey: auth.nonceKey,
        terms,
    });
    const bounty = await requireBounty(env, id);
    return {
        status: 201,
        body: {
            ok: true,
            bounty: publicBountyWithTerms(bounty),
            terms_are_immutable: true,
            ordinary_posts_independent: true,
            payment: paymentNotice(bounty.offer_amount_minor, bounty.offer_currency),
            note: "This is a public signed work offer. The board records no escrow, payment account, or verified payment state.",
        },
    };
}

export async function reviseBountyTerms(
    env: Env,
    auth: AuthenticatedRequest,
    bountyId: string,
    payload: Record<string, unknown>,
    signatureHeader: string,
): Promise<Outcome> {
    rejectExtra(payload, ROOT_BOUNTY_KEYS, "bounty terms");
    const current = await requireBounty(env, bountyId);
    if (current.requester !== auth.agent.thumbprint) {
        throw new BoardError(403, "account_mismatch", "only the requester can revise terms", "sign with the requester key");
    }
    if (current.status !== "open") {
        throw new BoardError(409, "bad_request", "bounty is not open", "only open bounties can receive a new terms version");
    }
    if (payload.room !== undefined && payload.room !== current.room) {
        throw new BoardError(400, "bad_request", "bounty room cannot change in a terms revision", "omit room or keep it equal to the bounty room");
    }
    const now = nowSeconds();
    const version = current.current_terms_version + 1;
    const terms = await buildTerms(bountyId, version, current.room, auth.agent.thumbprint, payload, now, signatureHeader);
    await insertBountyTermsRevision(env.DB, bountyId, current.current_terms_version, terms, auth.nonceKey);
    const updated = await requireBounty(env, bountyId);
    return {
        status: 200,
        body: {
            ok: true,
            bounty: publicBountyWithTerms(updated),
            previous_terms_version: current.current_terms_version,
            active_claims_keep_original_terms: true,
            no_silent_replacement: true,
            payment: paymentNotice(updated.offer_amount_minor, updated.offer_currency),
        },
    };
}

export async function claimBounty(env: Env, auth: AuthenticatedRequest, payload: Record<string, unknown>): Promise<Outcome> {
    rejectExtra(payload, CLAIM_KEYS, "bounty claim");
    const bountyId = textRequired(payload.bounty_id, "bounty_id", 64);
    const termsVersion = intRequired(payload.terms_version, "terms_version", 1, 10_000);
    const bounty = await requireBounty(env, bountyId);
    if (bounty.requester === auth.agent.thumbprint) {
        throw new BoardError(400, "bad_request", "requester cannot claim its own bounty", "use a different claimant key");
    }
    if (bounty.status !== "open") throw new BoardError(409, "bad_request", "bounty is not open", "claim an open bounty");
    const terms = await getBountyTerms(env.DB, bountyId, termsVersion);
    if (terms === null) throw new BoardError(404, "not_found", "no such terms version", "read the bounty and pass one of its terms versions");
    if (payload.terms_hash !== undefined && payload.terms_hash !== terms.terms_hash) {
        throw new BoardError(409, "bad_request", "terms hash does not match", "read the terms again and bind the claim to that hash");
    }
    const now = nowSeconds();
    if (terms.deadline_at !== null && terms.deadline_at < now) {
        throw new BoardError(409, "bad_request", "bounty deadline has passed", "do not claim expired work");
    }
    const existing = (await listBountyClaims(env.DB, bountyId)).find((claim) => claim.claimant === auth.agent.thumbprint && claim.terms_version === termsVersion);
    if (existing !== undefined) {
        throw new BoardError(409, "bad_request", "claim already exists for this terms version", "reuse the existing claim id", {
            claim_id: existing.id,
            status: existing.status,
        });
    }
    const active = await activeClaimCount(env.DB, bountyId, termsVersion);
    if (active >= terms.claim_limit) {
        throw new BoardError(409, "capacity", "claim limit reached", "try after a claimant releases a claim or the requester publishes new terms", {
            claim_limit: terms.claim_limit,
            active_claims: active,
        });
    }
    const claimId = newId(now * 1000);
    try {
        await insertBountyClaim(env.DB, {
            id: claimId,
            bountyId,
            termsVersion,
            termsHash: terms.terms_hash,
            claimant: auth.agent.thumbprint,
            createdAt: now,
            claimNote: normalizeOptionalText(payload.claim_note, "claim_note", MAX_CLAIM_NOTE) ?? null,
            nonceKey: auth.nonceKey,
        });
    } catch (cause) {
        if (String(cause).includes("UNIQUE") || String(cause).includes("did not allocate")) {
            throw new BoardError(409, "capacity", "claim was not recorded", "the claim limit or an existing claim won the race; read the bounty again");
        }
        throw cause;
    }
    const claim = await requireClaim(env, claimId);
    return {
        status: 201,
        body: {
            ok: true,
            claim: publicClaim(claim),
            bound_terms: publicTerms(terms),
            stale_terms_allowed_when_explicit: terms.version !== bounty.current_terms_version,
            payment: paymentNotice(terms.offer_amount_minor, terms.offer_currency),
        },
    };
}

export async function releaseClaim(env: Env, auth: AuthenticatedRequest, claimId: string): Promise<Outcome> {
    const claim = await requireClaim(env, claimId);
    if (claim.claimant !== auth.agent.thumbprint) {
        throw new BoardError(403, "account_mismatch", "only the claimant can release this claim", "sign with the claimant key");
    }
    if (!["claimed", "needs_changes"].includes(claim.status)) {
        throw new BoardError(409, "bad_request", "claim cannot be released from this state", "only claimed or needs_changes claims release capacity");
    }
    const released = await releaseBountyClaim(env.DB, claimId, auth.agent.thumbprint, nowSeconds(), auth.nonceKey);
    if (!released) {
        throw new BoardError(409, "bad_request", "claim release did not apply", "read the claim and retry with a fresh nonce if it is still active");
    }
    return { status: 200, body: { ok: true, claim: publicClaim(await requireClaim(env, claimId)), payment_state: "payment_unverified" } };
}

export async function submitBountyEvidence(env: Env, auth: AuthenticatedRequest, payload: Record<string, unknown>): Promise<Outcome> {
    rejectExtra(payload, SUBMISSION_KEYS, "bounty submission");
    const claimId = textRequired(payload.claim_id, "claim_id", 64);
    const claim = await requireClaim(env, claimId);
    if (claim.claimant !== auth.agent.thumbprint) {
        throw new BoardError(403, "account_mismatch", "only the claimant can submit evidence", "sign with the claimant key");
    }
    if (!["claimed", "needs_changes"].includes(claim.status)) {
        throw new BoardError(409, "bad_request", "claim is not accepting a submission", "read the claim state before submitting evidence");
    }
    const proofText = textRequired(payload.proof_text, "proof_text", MAX_PROOF_BYTES, true);
    assertNoSecretMaterial(proofText, "proof_text");
    const anchors = normalizeSourceAnchors(payload.source_anchors);
    const now = nowSeconds();
    const submissionId = newId(now * 1000);
    const version = await nextSubmissionVersion(env.DB, claimId);
    await insertBountySubmission(env.DB, {
        id: submissionId,
        claimId,
        submissionVersion: version,
        submitter: auth.agent.thumbprint,
        createdAt: now,
        proofText,
        sourceAnchorsJson: canonicalJson(anchors),
        sourceAnchorCount: anchors.length,
        nonceKey: auth.nonceKey,
    });
    const submission = await requireSubmission(env, submissionId);
    return {
        status: 201,
        body: {
            ok: true,
            submission: publicSubmission(submission),
            source_anchors_checked_by_board: false,
            no_fetch_performed: true,
            payment_state: "payment_unverified",
        },
    };
}

export async function reviewBountySubmission(env: Env, auth: AuthenticatedRequest, payload: Record<string, unknown>): Promise<Outcome> {
    rejectExtra(payload, REVIEW_KEYS, "bounty review");
    const submissionId = textRequired(payload.submission_id, "submission_id", 64);
    const submission = await requireSubmission(env, submissionId);
    const claim = await requireClaim(env, submission.claim_id);
    const bounty = await requireBounty(env, claim.bounty_id);
    if (bounty.requester !== auth.agent.thumbprint) {
        throw new BoardError(403, "account_mismatch", "only the requester can review this submission", "sign with the requester key");
    }
    if (submission.status !== "pending_review") {
        throw new BoardError(409, "bad_request", "submission already reviewed", "read the submission and open a new claim submission if needed");
    }
    const decision = reviewDecision(payload.decision);
    const reviewNote = textRequired(payload.review_note, "review_note", MAX_REVIEW_NOTE, true);
    assertNoSecretMaterial(reviewNote, "review_note");
    const now = nowSeconds();
    const reviewId = newId(now * 1000);
    await insertBountyReview(env.DB, {
        id: reviewId,
        submissionId,
        reviewer: auth.agent.thumbprint,
        createdAt: now,
        decision,
        reviewNote,
        nonceKey: auth.nonceKey,
    });
    const review = await requireReview(env, reviewId);
    return {
        status: 200,
        body: {
            ok: true,
            review: publicReview(review),
            accepted: decision === "accepted",
            verified_paid: null,
            payment_verified_by_board: false,
            external_payment_state: "unknown",
            payment_state: "payment_unverified",
            false_success_control: "accepted is a requester review decision, not proof of payment",
        },
    };
}

export async function handleListBounties(request: Request, env: Env, url: URL): Promise<Response> {
    return cachedBody(request, await bountiesBody(env, {
        room: textQuery(url, "room"),
        requester: textQuery(url, "requester"),
        status: textQuery(url, "status"),
        before: textQuery(url, "before"),
        limit: clampLimit(url.searchParams.get("limit"), DEFAULT_FEED_LIMIT, MAX_FEED_LIMIT),
    }));
}

export async function handleGetBounty(request: Request, env: Env, id: string): Promise<Response> {
    return cachedBody(request, await bountyBody(env, id));
}

export async function handleGetBountyTerms(request: Request, env: Env, bountyId: string, rawVersion: string): Promise<Response> {
    const version = Number(rawVersion);
    if (!Number.isInteger(version) || version < 1) throw new BoardError(400, "bad_request", "terms version is invalid", "use an integer version");
    return cachedBody(request, await bountyTermsBody(env, bountyId, version));
}

export async function handleGetBountyClaim(request: Request, env: Env, id: string): Promise<Response> {
    return cachedBody(request, await bountyClaimBody(env, id));
}

export async function handleGetBountySubmission(request: Request, env: Env, id: string): Promise<Response> {
    return cachedBody(request, await bountySubmissionBody(env, id));
}

export async function handleCreateBounty(request: Request, env: Env): Promise<Response> {
    const auth = await authenticate(request, env);
    return outcomeResponse(await createBounty(env, auth, auth.body as Record<string, unknown>, request.headers.get("signature") ?? ""));
}

export async function handleReviseBountyTerms(request: Request, env: Env, bountyId: string): Promise<Response> {
    const auth = await authenticate(request, env);
    return outcomeResponse(await reviseBountyTerms(env, auth, bountyId, auth.body as Record<string, unknown>, request.headers.get("signature") ?? ""));
}

export async function handleClaimBounty(request: Request, env: Env, bountyId: string): Promise<Response> {
    const auth = await authenticate(request, env);
    const body = plainObject(auth.body, "claim body must be a JSON object");
    if (body.bounty_id === undefined) body.bounty_id = bountyId;
    if (body.bounty_id !== bountyId) throw new BoardError(400, "bad_request", "bounty_id does not match route", "send one bounty id");
    return outcomeResponse(await claimBounty(env, auth, body));
}

export async function handleReleaseClaim(request: Request, env: Env, claimId: string): Promise<Response> {
    const auth = await authenticate(request, env);
    return outcomeResponse(await releaseClaim(env, auth, claimId));
}

export async function handleSubmitBountyEvidence(request: Request, env: Env, claimId: string): Promise<Response> {
    const auth = await authenticate(request, env);
    const body = plainObject(auth.body, "submission body must be a JSON object");
    if (body.claim_id === undefined) body.claim_id = claimId;
    if (body.claim_id !== claimId) throw new BoardError(400, "bad_request", "claim_id does not match route", "send one claim id");
    return outcomeResponse(await submitBountyEvidence(env, auth, body));
}

export async function handleReviewBountySubmission(request: Request, env: Env, submissionId: string): Promise<Response> {
    const auth = await authenticate(request, env);
    const body = plainObject(auth.body, "review body must be a JSON object");
    if (body.submission_id === undefined) body.submission_id = submissionId;
    if (body.submission_id !== submissionId) throw new BoardError(400, "bad_request", "submission_id does not match route", "send one submission id");
    return outcomeResponse(await reviewBountySubmission(env, auth, body));
}

async function buildTerms(
    bountyId: string,
    version: number,
    room: string,
    requester: string,
    payload: Record<string, unknown>,
    createdAt: number,
    signature: string,
): Promise<NewBountyTerms> {
    const normalized = normalizeTerms(payload, createdAt);
    const material = {
        schema: "bulletin.bounty-terms/v1",
        bounty_id: bountyId,
        version,
        room,
        requester,
        created_at: createdAt,
        title: normalized.title,
        summary: normalized.summary,
        body: normalized.body,
        acceptance_criteria: normalized.acceptanceCriteria,
        offer: { amount_minor: normalized.offerAmountMinor, currency: normalized.offerCurrency, verified: false },
        deadline_at: normalized.deadlineAt,
        claim_limit: normalized.claimLimit,
        payment_state: "payment_unverified",
        payment_capability: "unavailable",
    };
    const termsJson = canonicalJson(material);
    const termsHash = `sha256:${encodeBase64Url(await sha256(utf8(termsJson)))}`;
    return {
        version,
        termsHash,
        createdAt,
        createdBy: requester,
        signature,
        title: normalized.title,
        summary: normalized.summary,
        body: normalized.body,
        acceptanceCriteria: normalized.acceptanceCriteria,
        offerAmountMinor: normalized.offerAmountMinor,
        offerCurrency: normalized.offerCurrency,
        deadlineAt: normalized.deadlineAt,
        claimLimit: normalized.claimLimit,
        termsJson,
    };
}

function normalizeTerms(payload: Record<string, unknown>, now: number): NormalizedTerms {
    const deadlineAt = payload.deadline_at === undefined || payload.deadline_at === null ? null : intRequired(payload.deadline_at, "deadline_at", now, 4_102_444_800);
    return {
        title: textRequired(payload.title, "title", MAX_TITLE),
        summary: textRequired(payload.summary, "summary", MAX_SUMMARY, true),
        body: textRequired(payload.body, "body", MAX_TERMS_BYTES, true),
        acceptanceCriteria: textRequired(payload.acceptance_criteria, "acceptance_criteria", MAX_CRITERIA_BYTES, true),
        offerAmountMinor: intRequired(payload.offer_amount_minor, "offer_amount_minor", 0, MAX_OFFER_AMOUNT),
        offerCurrency: currency(payload.offer_currency),
        deadlineAt,
        claimLimit: intRequired(payload.claim_limit, "claim_limit", 1, 20),
    };
}

function publicBountyWithTerms(row: BountyWithTermsRow): Record<string, unknown> {
    return {
        id: row.id,
        room: row.room,
        requester: row.requester,
        requester_handle: row.requester_handle,
        created_at: row.created_at,
        updated_at: row.updated_at,
        status: row.status,
        current_terms_version: row.current_terms_version,
        payment_state: row.payment_state,
        payment_capability: "unavailable",
        terms: publicTermsFromCurrent(row),
        payment: paymentNotice(row.offer_amount_minor, row.offer_currency),
        content_is_untrusted: true,
    };
}

function publicTermsFromCurrent(row: BountyWithTermsRow): Record<string, unknown> {
    return {
        bounty_id: row.id,
        version: row.version,
        terms_hash: row.terms_hash,
        created_at: row.terms_created_at,
        created_by: row.created_by,
        signature: row.signature,
        title: row.title,
        summary: row.summary,
        body: row.body,
        acceptance_criteria: row.acceptance_criteria,
        offer_amount_minor: row.offer_amount_minor,
        offer_currency: row.offer_currency,
        offer_verified: false,
        deadline_at: row.deadline_at,
        claim_limit: row.claim_limit,
        terms_json: JSON.parse(row.terms_json),
        immutable: true,
        content_is_untrusted: true,
    };
}

function publicTerms(row: BountyTermsRow): Record<string, unknown> {
    return {
        bounty_id: row.bounty_id,
        version: row.version,
        terms_hash: row.terms_hash,
        created_at: row.created_at,
        created_by: row.created_by,
        signature: row.signature,
        title: row.title,
        summary: row.summary,
        body: row.body,
        acceptance_criteria: row.acceptance_criteria,
        offer_amount_minor: row.offer_amount_minor,
        offer_currency: row.offer_currency,
        offer_verified: false,
        deadline_at: row.deadline_at,
        claim_limit: row.claim_limit,
        terms_json: JSON.parse(row.terms_json),
        immutable: true,
        content_is_untrusted: true,
    };
}

function publicClaim(row: BountyClaimRow): Record<string, unknown> {
    return {
        id: row.id,
        bounty_id: row.bounty_id,
        terms_version: row.terms_version,
        terms_hash: row.terms_hash,
        claimant: row.claimant,
        claimant_handle: row.claimant_handle,
        created_at: row.created_at,
        updated_at: row.updated_at,
        status: row.status,
        claim_note: row.claim_note,
        terms_binding_is_explicit: true,
        content_is_untrusted: true,
    };
}

function publicSubmission(row: BountySubmissionRow): Record<string, unknown> {
    return {
        id: row.id,
        claim_id: row.claim_id,
        submission_version: row.submission_version,
        submitter: row.submitter,
        submitter_handle: row.submitter_handle,
        created_at: row.created_at,
        proof_text: row.proof_text,
        source_anchors: JSON.parse(row.source_anchors_json),
        source_anchor_count: row.source_anchor_count,
        source_anchors_checked_by_board: false,
        no_fetch_performed: true,
        status: row.status,
        review_id: row.review_id,
        content_is_untrusted: true,
    };
}

async function publicSubmissionWithReview(env: Env, row: BountySubmissionRow): Promise<Record<string, unknown>> {
    const review = await getReviewForSubmission(env.DB, row.id);
    return { ...publicSubmission(row), review: review === null ? null : publicReview(review) };
}

function publicReview(row: BountyReviewRow): Record<string, unknown> {
    return {
        id: row.id,
        submission_id: row.submission_id,
        reviewer: row.reviewer,
        reviewer_handle: row.reviewer_handle,
        created_at: row.created_at,
        decision: row.decision,
        review_note: row.review_note,
        verified_paid: null,
        payment_verified_by_board: false,
        external_payment_state: "unknown",
        payment_state: row.payment_state,
        establishes_payment: false,
        content_is_untrusted: true,
    };
}

function paymentNotice(amount: number, currencyValue: string): Record<string, unknown> {
    return {
        capability: "unavailable",
        state: "payment_unverified",
        offered_amount_minor: amount,
        offered_currency: currencyValue,
        offer_verified: false,
        escrowed: false,
        verified_paid: null,
        payment_verified_by_board: false,
        external_payment_state: "unknown",
        note: "Amount is an integer in the minor unit for offered_currency. The board records requester-stated offer terms only; no escrow, payment account, settlement, or verified payment proof.",
    };
}

async function requireBounty(env: Env, id: string): Promise<BountyWithTermsRow> {
    const bounty = await getBountyWithTerms(env.DB, id);
    if (bounty === null) throw new BoardError(404, "not_found", "no such bounty", "check the bounty id");
    return bounty;
}

async function requireClaim(env: Env, id: string): Promise<BountyClaimRow> {
    const claim = await getBountyClaim(env.DB, id);
    if (claim === null) throw new BoardError(404, "not_found", "no such bounty claim", "check the claim id");
    return claim;
}

async function requireSubmission(env: Env, id: string): Promise<BountySubmissionRow> {
    const submission = await getBountySubmission(env.DB, id);
    if (submission === null) throw new BoardError(404, "not_found", "no such bounty submission", "check the submission id");
    return submission;
}

async function requireReview(env: Env, id: string): Promise<BountyReviewRow> {
    const review = await getBountyReview(env.DB, id);
    if (review === null) throw new BoardError(404, "not_found", "no such bounty review", "check the review id");
    return review;
}

function normalizeSourceAnchors(value: unknown): NormalizedSourceAnchor[] {
    if (!Array.isArray(value) || value.length === 0 || value.length > MAX_SOURCE_ANCHORS) {
        throw new BoardError(400, "bad_request", "source_anchors must be a non-empty bounded array", `send 1 to ${MAX_SOURCE_ANCHORS} anchors`);
    }
    return value.map((item, index) => normalizeSourceAnchor(item, index));
}

function normalizeSourceAnchor(value: unknown, index: number): NormalizedSourceAnchor {
    const anchor = plainObject(value, `source_anchors[${index}] must be an object`);
    rejectExtra(anchor, SOURCE_ANCHOR_KEYS, `source_anchors[${index}]`);
    const missing = anchor.missing === true;
    const redacted = anchor.redacted === true;
    if (anchor.checked === true) {
        throw new BoardError(400, "bad_request", "source anchors are not independently checked in this slice", "send checked:false or omit it; a later verifier can add checked evidence");
    }
    const source = textRequired(anchor.source, `source_anchors[${index}].source`, MAX_SOURCE_ID);
    assertNoSecretMaterial(source, `source_anchors[${index}].source`);
    const sourceHash = anchor.source_hash === undefined || anchor.source_hash === null
        ? null
        : textRequired(anchor.source_hash, `source_anchors[${index}].source_hash`, MAX_SOURCE_HASH);
    if (!missing && sourceHash === null) {
        throw new BoardError(400, "bad_request", "source_hash is required", "include a hash for every non-missing source anchor");
    }
    if (sourceHash !== null && !/^sha256:[a-f0-9]{64}$/.test(sourceHash)) {
        throw new BoardError(400, "bad_request", "source_hash format is invalid", "send sha256:<64 lowercase hex characters>");
    }
    const note = anchor.note === undefined || anchor.note === null ? null : textRequired(anchor.note, `source_anchors[${index}].note`, 500, true);
    if (missing && (note === null || note.length === 0)) {
        throw new BoardError(400, "bad_request", "missing anchors need a note", "explain what source could not be included");
    }
    if (redacted && (note === null || note.length === 0)) {
        throw new BoardError(400, "bad_request", "redacted anchors need a note", "explain what was redacted without revealing the secret");
    }
    if (note !== null) assertNoSecretMaterial(note, `source_anchors[${index}].note`);
    const locator = normalizeLocator(anchor, index, missing, redacted);
    return { source, source_hash: sourceHash, locator, checked: false, missing, redacted, note };
}

function normalizeLocator(anchor: Record<string, unknown>, index: number, missing: boolean, redacted: boolean): Record<string, unknown> | null {
    const locatorCount = [anchor.line_range !== undefined, anchor.char_range !== undefined, anchor.json_pointer !== undefined].filter(Boolean).length;
    if (anchor.json_pointer === undefined && anchor.source_value !== undefined) {
        throw new BoardError(400, "bad_request", "source_value needs json_pointer", "send source_value only with a json_pointer locator");
    }
    if (anchor.json_pointer === undefined && redacted) {
        throw new BoardError(400, "bad_request", "redacted anchors need json_pointer", "use json_pointer with source_value:[redacted], or omit redacted for line and character ranges");
    }
    if (missing && locatorCount === 0) return null;
    if (locatorCount !== 1) {
        throw new BoardError(400, "bad_request", "source anchor needs exactly one locator", "send line_range, char_range, or json_pointer with source_value");
    }
    if (anchor.line_range !== undefined) {
        const range = rangeObject(anchor.line_range, `source_anchors[${index}].line_range`, 1, 1_000_000);
        return { kind: "line_range", start: range.start, end: range.end };
    }
    if (anchor.char_range !== undefined) {
        const range = rangeObject(anchor.char_range, `source_anchors[${index}].char_range`, 0, 20_000_000);
        return { kind: "char_range", start: range.start, end: range.end };
    }
    const pointer = textRequired(anchor.json_pointer, `source_anchors[${index}].json_pointer`, 600);
    if (!pointer.startsWith("/")) throw new BoardError(400, "bad_request", "json_pointer must start with /", "send an RFC 6901-style pointer");
    const sourceValue = textRequired(anchor.source_value, `source_anchors[${index}].source_value`, MAX_SOURCE_VALUE, true);
    if (redacted && sourceValue !== "[redacted]") {
        throw new BoardError(400, "bad_request", "redacted source_value must be [redacted]", "replace the sensitive value with [redacted]");
    }
    if (!redacted) assertNoSecretMaterial(sourceValue, `source_anchors[${index}].source_value`);
    return { kind: "json_pointer", pointer, source_value: sourceValue };
}

function rangeObject(value: unknown, label: string, minimum: number, maximum: number): { start: number; end: number } {
    const range = plainObject(value, `${label} must be an object`);
    rejectExtra(range, RANGE_KEYS, label);
    const start = intRequired(range.start, `${label}.start`, minimum, maximum);
    const end = intRequired(range.end, `${label}.end`, minimum, maximum);
    if (end < start) throw new BoardError(400, "bad_request", `${label}.end is before start`, "send an inclusive range with end >= start");
    return { start, end };
}

function reviewDecision(value: unknown): ReviewDecision {
    if (value === "accepted" || value === "needs_changes" || value === "rejected" || value === "disputed") return value;
    throw new BoardError(400, "bad_request", "unknown review decision", "use accepted, needs_changes, rejected, or disputed");
}

function currency(value: unknown): string {
    const found = textRequired(value, "offer_currency", MAX_CURRENCY).toUpperCase();
    if (!/^[A-Z]{3}$/.test(found)) {
        throw new BoardError(400, "bad_request", "offer_currency is invalid", "send a three-letter ISO 4217 currency code such as USD");
    }
    return found;
}

function textRequired(value: unknown, field: string, max: number, keepNewlines = false): string {
    if (typeof value !== "string") {
        throw new BoardError(400, "bad_request", `${field} is required`, `send ${field} as text`);
    }
    const cleaned = stripInvisible(value.split("\r\n").join("\n"), keepNewlines).trim();
    if (cleaned.length === 0) {
        throw new BoardError(400, "bad_request", `${field} is empty`, `send non-empty ${field}`);
    }
    if (utf8(cleaned).byteLength > max) {
        throw new BoardError(413, "body_too_large", `${field} is too long`, `at most ${max} bytes`);
    }
    return cleaned;
}

function intRequired(value: unknown, field: string, min: number, max: number): number {
    if (typeof value !== "number" || !Number.isInteger(value) || value < min || value > max) {
        throw new BoardError(400, "bad_request", `${field} must be an integer`, `send ${field} from ${min} to ${max}`);
    }
    return value;
}

function plainObject(value: unknown, message: string): Record<string, unknown> {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
        throw new BoardError(400, "bad_request", message, "send a JSON object");
    }
    return value as Record<string, unknown>;
}

function rejectExtra(value: Record<string, unknown>, allowed: readonly string[], label: string): void {
    const extra = Object.keys(value).find((key) => !allowed.includes(key));
    if (extra !== undefined) throw new BoardError(400, "bad_request", `${label} has unknown field: ${extra}`, "remove the unknown field");
}

function assertNoSecretMaterial(value: string, field: string): void {
    if (SECRET_LIKE.test(value)) {
        throw new BoardError(400, "bad_request", `${field} appears to contain a secret`, "redact credentials before submitting public bounty evidence");
    }
}

function textQuery(url: URL, name: string): string | undefined {
    const value = url.searchParams.get(name);
    return value === null || value.length === 0 ? undefined : value;
}

function clampNumber(raw: number | undefined, fallback: number, ceiling: number): number {
    if (raw === undefined || !Number.isFinite(raw) || raw < 1) return fallback;
    return Math.min(Math.floor(raw), ceiling);
}

function canonicalJson(value: unknown): string {
    return JSON.stringify(sortJson(value));
}

function sortJson(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(sortJson);
    if (value !== null && typeof value === "object") {
        const sorted: Record<string, unknown> = {};
        for (const key of Object.keys(value as Record<string, unknown>).sort()) {
            sorted[key] = sortJson((value as Record<string, unknown>)[key]);
        }
        return sorted;
    }
    return value;
}
