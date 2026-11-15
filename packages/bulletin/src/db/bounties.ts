/**
 * Bounty rows.
 *
 * Bounties add a work-offer ledger to the board without adding a payment rail.
 * The database stores immutable terms, bounded public claims, evidence
 * submissions, and requester reviews. A review can accept the work, but payment
 * remains an unverified outside fact and is constrained as such in the schema.
 */

export type BountyStatus = "open" | "closed" | "cancelled";
export type ClaimStatus = "claimed" | "submitted" | "needs_changes" | "accepted" | "rejected" | "released" | "disputed";
export type SubmissionStatus = "pending_review" | "needs_changes" | "accepted" | "rejected" | "disputed";
export type ReviewDecision = "accepted" | "needs_changes" | "rejected" | "disputed";

export interface BountyRow {
    id: string;
    room: string;
    requester: string;
    requester_handle: string | null;
    created_at: number;
    updated_at: number;
    status: BountyStatus;
    current_terms_version: number;
    payment_state: "payment_unverified";
}

export interface BountyTermsRow {
    bounty_id: string;
    version: number;
    terms_hash: string;
    created_at: number;
    created_by: string;
    signature: string;
    title: string;
    summary: string;
    body: string;
    acceptance_criteria: string;
    offer_amount_minor: number;
    offer_currency: string;
    deadline_at: number | null;
    claim_limit: number;
    terms_json: string;
}

export interface BountyWithTermsRow extends BountyRow {
    version: number;
    terms_hash: string;
    terms_created_at: number;
    created_by: string;
    signature: string;
    title: string;
    summary: string;
    body: string;
    acceptance_criteria: string;
    offer_amount_minor: number;
    offer_currency: string;
    deadline_at: number | null;
    claim_limit: number;
    terms_json: string;
}

export interface BountyClaimRow {
    id: string;
    bounty_id: string;
    terms_version: number;
    terms_hash: string;
    claimant: string;
    claimant_handle: string | null;
    created_at: number;
    updated_at: number;
    status: ClaimStatus;
    claim_note: string | null;
}

export interface BountySubmissionRow {
    id: string;
    claim_id: string;
    submission_version: number;
    submitter: string;
    submitter_handle: string | null;
    created_at: number;
    proof_text: string;
    source_anchors_json: string;
    source_anchor_count: number;
    status: SubmissionStatus;
    review_id: string | null;
}

export interface BountyReviewRow {
    id: string;
    submission_id: string;
    reviewer: string;
    reviewer_handle: string | null;
    created_at: number;
    decision: ReviewDecision;
    review_note: string;
    payment_verified_by_board: 0;
    payment_state: "payment_unverified";
}

export interface NewBounty {
    id: string;
    room: string;
    requester: string;
    createdAt: number;
    nonceKey: string;
    terms: NewBountyTerms;
}

export interface NewBountyTerms {
    version: number;
    termsHash: string;
    createdAt: number;
    createdBy: string;
    signature: string;
    title: string;
    summary: string;
    body: string;
    acceptanceCriteria: string;
    offerAmountMinor: number;
    offerCurrency: string;
    deadlineAt: number | null;
    claimLimit: number;
    termsJson: string;
}

export interface NewBountyClaim {
    id: string;
    bountyId: string;
    termsVersion: number;
    termsHash: string;
    claimant: string;
    createdAt: number;
    claimNote: string | null;
    nonceKey: string;
}

export interface NewBountySubmission {
    id: string;
    claimId: string;
    submissionVersion: number;
    submitter: string;
    createdAt: number;
    proofText: string;
    sourceAnchorsJson: string;
    sourceAnchorCount: number;
    nonceKey: string;
}

export interface NewBountyReview {
    id: string;
    submissionId: string;
    reviewer: string;
    createdAt: number;
    decision: ReviewDecision;
    reviewNote: string;
    nonceKey: string;
}

const BOUNTY_SELECT =
    `SELECT b.*, agents.handle AS requester_handle,
            t.bounty_id, t.version, t.terms_hash, t.created_at AS terms_created_at,
            t.created_by, t.signature, t.title, t.summary, t.body, t.acceptance_criteria,
            t.offer_amount_minor, t.offer_currency, t.deadline_at, t.claim_limit, t.terms_json
       FROM bounties b
       JOIN bounty_terms t ON t.bounty_id = b.id AND t.version = b.current_terms_version
       LEFT JOIN agents ON agents.thumbprint = b.requester`;

const CLAIM_SELECT =
    `SELECT c.*, agents.handle AS claimant_handle
       FROM bounty_claims c
       LEFT JOIN agents ON agents.thumbprint = c.claimant`;

const SUBMISSION_SELECT =
    `SELECT s.*, agents.handle AS submitter_handle
       FROM bounty_submissions s
       LEFT JOIN agents ON agents.thumbprint = s.submitter`;

const REVIEW_SELECT =
    `SELECT r.*, agents.handle AS reviewer_handle
       FROM bounty_reviews r
       LEFT JOIN agents ON agents.thumbprint = r.reviewer`;

export async function listBounties(
    db: D1Database,
    query: { room?: string | undefined; requester?: string | undefined; status?: string | undefined; before?: string | undefined; limit: number },
): Promise<BountyWithTermsRow[]> {
    const clauses: string[] = [];
    const values: unknown[] = [];
    if (query.room !== undefined) {
        clauses.push("b.room = ?");
        values.push(query.room);
    }
    if (query.requester !== undefined) {
        clauses.push("b.requester = ?");
        values.push(query.requester);
    }
    if (query.status !== undefined) {
        clauses.push("b.status = ?");
        values.push(query.status);
    }
    if (query.before !== undefined) {
        clauses.push("b.id < ?");
        values.push(query.before);
    }
    const where = clauses.length === 0 ? "" : `WHERE ${clauses.join(" AND ")}`;
    const result = await db.prepare(`${BOUNTY_SELECT} ${where} ORDER BY b.id DESC LIMIT ?`).bind(...values, query.limit).all<BountyWithTermsRow>();
    return result.results ?? [];
}

export async function getBountyWithTerms(db: D1Database, id: string): Promise<BountyWithTermsRow | null> {
    return db.prepare(`${BOUNTY_SELECT} WHERE b.id = ?`).bind(id).first<BountyWithTermsRow>();
}

export async function getBountyTerms(db: D1Database, bountyId: string, version: number): Promise<BountyTermsRow | null> {
    return db.prepare("SELECT * FROM bounty_terms WHERE bounty_id = ? AND version = ?")
        .bind(bountyId, version)
        .first<BountyTermsRow>();
}

export async function listBountyClaims(db: D1Database, bountyId: string): Promise<BountyClaimRow[]> {
    const result = await db.prepare(`${CLAIM_SELECT} WHERE c.bounty_id = ? ORDER BY c.id DESC`).bind(bountyId).all<BountyClaimRow>();
    return result.results ?? [];
}

export async function getBountyClaim(db: D1Database, id: string): Promise<BountyClaimRow | null> {
    return db.prepare(`${CLAIM_SELECT} WHERE c.id = ?`).bind(id).first<BountyClaimRow>();
}

export async function listClaimSubmissions(db: D1Database, claimId: string): Promise<BountySubmissionRow[]> {
    const result = await db.prepare(`${SUBMISSION_SELECT} WHERE s.claim_id = ? ORDER BY s.submission_version DESC`).bind(claimId).all<BountySubmissionRow>();
    return result.results ?? [];
}

export async function getBountySubmission(db: D1Database, id: string): Promise<BountySubmissionRow | null> {
    return db.prepare(`${SUBMISSION_SELECT} WHERE s.id = ?`).bind(id).first<BountySubmissionRow>();
}

export async function getBountyReview(db: D1Database, id: string): Promise<BountyReviewRow | null> {
    return db.prepare(`${REVIEW_SELECT} WHERE r.id = ?`).bind(id).first<BountyReviewRow>();
}

export async function getReviewForSubmission(db: D1Database, submissionId: string): Promise<BountyReviewRow | null> {
    return db.prepare(`${REVIEW_SELECT} WHERE r.submission_id = ?`).bind(submissionId).first<BountyReviewRow>();
}

export async function nextSubmissionVersion(db: D1Database, claimId: string): Promise<number> {
    const row = await db.prepare("SELECT COALESCE(MAX(submission_version), 0) + 1 AS next FROM bounty_submissions WHERE claim_id = ?")
        .bind(claimId)
        .first<{ next: number }>();
    return Math.max(1, Math.floor(row?.next ?? 1));
}

export async function activeClaimCount(db: D1Database, bountyId: string, termsVersion: number): Promise<number> {
    const row = await db.prepare(
        `SELECT COUNT(*) AS count
           FROM bounty_claims
          WHERE bounty_id = ? AND terms_version = ? AND status IN ('claimed', 'submitted', 'needs_changes')`,
    ).bind(bountyId, termsVersion).first<{ count: number }>();
    return Math.floor(row?.count ?? 0);
}

export async function insertBountyWithTerms(db: D1Database, bounty: NewBounty): Promise<string> {
    const t = bounty.terms;
    const results = await db.batch([
        db.prepare("UPDATE spent_nonces SET result_kind = 'bounty_pending', result_id = ? WHERE nonce = ? AND result_kind IS NULL AND result_id IS NULL")
            .bind(bounty.id, bounty.nonceKey),
        db.prepare(
            `INSERT INTO bounties (id, room, requester, created_at, updated_at, status, current_terms_version, payment_state)
             SELECT ?, ?, ?, ?, ?, 'open', 1, 'payment_unverified'
               FROM spent_nonces
              WHERE nonce = ? AND result_kind = 'bounty_pending' AND result_id = ?`,
        ).bind(bounty.id, bounty.room, bounty.requester, bounty.createdAt, bounty.createdAt, bounty.nonceKey, bounty.id),
        db.prepare(
            `INSERT INTO bounty_terms (
                bounty_id, version, terms_hash, created_at, created_by, signature, title, summary, body,
                acceptance_criteria, offer_amount_minor, offer_currency, deadline_at, claim_limit, terms_json
             )
             SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
               FROM spent_nonces
              WHERE nonce = ? AND result_kind = 'bounty_pending' AND result_id = ?`,
        ).bind(
            bounty.id,
            t.version,
            t.termsHash,
            t.createdAt,
            t.createdBy,
            t.signature,
            t.title,
            t.summary,
            t.body,
            t.acceptanceCriteria,
            t.offerAmountMinor,
            t.offerCurrency,
            t.deadlineAt,
            t.claimLimit,
            t.termsJson,
            bounty.nonceKey,
            bounty.id,
        ),
        db.prepare(
            `UPDATE spent_nonces
                SET result_kind = 'bounty'
              WHERE nonce = ? AND result_kind = 'bounty_pending'
                AND EXISTS (SELECT 1 FROM bounties WHERE id = spent_nonces.result_id)`,
        ).bind(bounty.nonceKey),
        db.prepare(
            `UPDATE spent_nonces SET result_kind = NULL, result_id = NULL
              WHERE nonce = ? AND result_kind = 'bounty_pending'
                AND NOT EXISTS (SELECT 1 FROM bounties WHERE id = ?)`,
        ).bind(bounty.nonceKey, bounty.id),
        db.prepare("SELECT result_id AS id FROM spent_nonces WHERE nonce = ? AND result_kind = 'bounty' AND result_id IS NOT NULL")
            .bind(bounty.nonceKey),
    ]);
    return oneAllocatedId(results, "bounty insert did not allocate an id");
}

export async function insertBountyTermsRevision(db: D1Database, bountyId: string, currentVersion: number, terms: NewBountyTerms, nonceKey: string): Promise<string> {
    const resultId = `${bountyId}:${terms.version}`;
    const results = await db.batch([
        db.prepare("UPDATE spent_nonces SET result_kind = 'bounty_terms_pending', result_id = ? WHERE nonce = ? AND result_kind IS NULL AND result_id IS NULL")
            .bind(resultId, nonceKey),
        db.prepare(
            `INSERT INTO bounty_terms (
                bounty_id, version, terms_hash, created_at, created_by, signature, title, summary, body,
                acceptance_criteria, offer_amount_minor, offer_currency, deadline_at, claim_limit, terms_json
             )
             SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
               FROM spent_nonces
              WHERE nonce = ? AND result_kind = 'bounty_terms_pending' AND result_id = ?
                AND EXISTS (SELECT 1 FROM bounties WHERE id = ? AND current_terms_version = ? AND status = 'open')`,
        ).bind(
            bountyId,
            terms.version,
            terms.termsHash,
            terms.createdAt,
            terms.createdBy,
            terms.signature,
            terms.title,
            terms.summary,
            terms.body,
            terms.acceptanceCriteria,
            terms.offerAmountMinor,
            terms.offerCurrency,
            terms.deadlineAt,
            terms.claimLimit,
            terms.termsJson,
            nonceKey,
            resultId,
            bountyId,
            currentVersion,
        ),
        db.prepare(
            `UPDATE bounties
                SET current_terms_version = ?, updated_at = ?
              WHERE id = ? AND current_terms_version = ? AND status = 'open'`,
        ).bind(terms.version, terms.createdAt, bountyId, currentVersion),
        db.prepare(
            `UPDATE spent_nonces
                SET result_kind = 'bounty_terms'
              WHERE nonce = ? AND result_kind = 'bounty_terms_pending'
                AND EXISTS (SELECT 1 FROM bounties WHERE id = ? AND current_terms_version = ?)`,
        ).bind(nonceKey, bountyId, terms.version),
        db.prepare(
            `UPDATE spent_nonces SET result_kind = NULL, result_id = NULL
              WHERE nonce = ? AND result_kind = 'bounty_terms_pending'
                AND NOT EXISTS (SELECT 1 FROM bounties WHERE id = ? AND current_terms_version = ?)`,
        ).bind(nonceKey, bountyId, terms.version),
        db.prepare("SELECT result_id AS id FROM spent_nonces WHERE nonce = ? AND result_kind = 'bounty_terms' AND result_id IS NOT NULL")
            .bind(nonceKey),
    ]);
    return oneAllocatedId(results, "bounty terms revision did not apply");
}

export async function insertBountyClaim(db: D1Database, claim: NewBountyClaim): Promise<string> {
    const results = await db.batch([
        db.prepare("UPDATE spent_nonces SET result_kind = 'bounty_claim_pending', result_id = ? WHERE nonce = ? AND result_kind IS NULL AND result_id IS NULL")
            .bind(claim.id, claim.nonceKey),
        db.prepare(
            `INSERT INTO bounty_claims (id, bounty_id, terms_version, terms_hash, claimant, created_at, updated_at, status, claim_note)
             SELECT ?, ?, ?, ?, ?, ?, ?, 'claimed', ?
              WHERE EXISTS (SELECT 1 FROM spent_nonces WHERE nonce = ? AND result_kind = 'bounty_claim_pending' AND result_id = ?)
                AND EXISTS (SELECT 1 FROM bounties WHERE id = ? AND status = 'open')
                AND (SELECT COUNT(*) FROM bounty_claims
                      WHERE bounty_id = ? AND terms_version = ? AND status IN ('claimed', 'submitted', 'needs_changes'))
                    < (SELECT claim_limit FROM bounty_terms WHERE bounty_id = ? AND version = ?)`,
        ).bind(
            claim.id,
            claim.bountyId,
            claim.termsVersion,
            claim.termsHash,
            claim.claimant,
            claim.createdAt,
            claim.createdAt,
            claim.claimNote,
            claim.nonceKey,
            claim.id,
            claim.bountyId,
            claim.bountyId,
            claim.termsVersion,
            claim.bountyId,
            claim.termsVersion,
        ),
        db.prepare(
            `UPDATE spent_nonces
                SET result_kind = 'bounty_claim'
              WHERE nonce = ? AND result_kind = 'bounty_claim_pending'
                AND EXISTS (SELECT 1 FROM bounty_claims WHERE id = spent_nonces.result_id)`,
        ).bind(claim.nonceKey),
        db.prepare(
            `UPDATE spent_nonces SET result_kind = NULL, result_id = NULL
              WHERE nonce = ? AND result_kind = 'bounty_claim_pending'
                AND NOT EXISTS (SELECT 1 FROM bounty_claims WHERE id = ?)`,
        ).bind(claim.nonceKey, claim.id),
        db.prepare("SELECT result_id AS id FROM spent_nonces WHERE nonce = ? AND result_kind = 'bounty_claim' AND result_id IS NOT NULL")
            .bind(claim.nonceKey),
    ]);
    return oneAllocatedId(results, "bounty claim did not allocate an id");
}

export async function releaseBountyClaim(db: D1Database, claimId: string, claimant: string, nowSeconds: number, nonceKey: string): Promise<boolean> {
    const results = await db.batch([
        db.prepare("UPDATE spent_nonces SET result_kind = 'bounty_claim_release_pending', result_id = ? WHERE nonce = ? AND result_kind IS NULL AND result_id IS NULL")
            .bind(claimId, nonceKey),
        db.prepare(
            `UPDATE bounty_claims
                SET status = 'released', updated_at = ?, last_transition_nonce = ?
              WHERE id = ? AND claimant = ? AND status IN ('claimed', 'needs_changes')
                AND EXISTS (SELECT 1 FROM spent_nonces WHERE nonce = ? AND result_kind = 'bounty_claim_release_pending' AND result_id = ?)`,
        ).bind(nowSeconds, nonceKey, claimId, claimant, nonceKey, claimId),
        db.prepare(
            `UPDATE spent_nonces
                SET result_kind = 'bounty_claim_release'
              WHERE nonce = ? AND result_kind = 'bounty_claim_release_pending'
                AND EXISTS (SELECT 1 FROM bounty_claims WHERE id = ? AND status = 'released' AND last_transition_nonce = ?)`,
        ).bind(nonceKey, claimId, nonceKey),
        db.prepare(
            `UPDATE spent_nonces SET result_kind = NULL, result_id = NULL
              WHERE nonce = ? AND result_kind = 'bounty_claim_release_pending'
                AND NOT EXISTS (SELECT 1 FROM bounty_claims WHERE id = ? AND status = 'released' AND last_transition_nonce = ?)`,
        ).bind(nonceKey, claimId, nonceKey),
        db.prepare("SELECT result_id AS id FROM spent_nonces WHERE nonce = ? AND result_kind = 'bounty_claim_release' AND result_id IS NOT NULL")
            .bind(nonceKey),
    ]);
    try {
        oneAllocatedId(results, "bounty claim release did not apply");
        return true;
    } catch {
        return false;
    }
}

export async function insertBountySubmission(db: D1Database, submission: NewBountySubmission): Promise<string> {
    const results = await db.batch([
        db.prepare("UPDATE spent_nonces SET result_kind = 'bounty_submission_pending', result_id = ? WHERE nonce = ? AND result_kind IS NULL AND result_id IS NULL")
            .bind(submission.id, submission.nonceKey),
        db.prepare(
            `INSERT INTO bounty_submissions (
                id, claim_id, submission_version, submitter, created_at, proof_text,
                source_anchors_json, source_anchor_count, status
             )
             SELECT ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review'
              WHERE EXISTS (SELECT 1 FROM spent_nonces WHERE nonce = ? AND result_kind = 'bounty_submission_pending' AND result_id = ?)
                AND EXISTS (SELECT 1 FROM bounty_claims WHERE id = ? AND claimant = ? AND status IN ('claimed', 'needs_changes'))`,
        ).bind(
            submission.id,
            submission.claimId,
            submission.submissionVersion,
            submission.submitter,
            submission.createdAt,
            submission.proofText,
            submission.sourceAnchorsJson,
            submission.sourceAnchorCount,
            submission.nonceKey,
            submission.id,
            submission.claimId,
            submission.submitter,
        ),
        db.prepare(
            `UPDATE bounty_claims
                SET status = 'submitted', updated_at = ?
              WHERE id = ? AND claimant = ?
                AND EXISTS (SELECT 1 FROM bounty_submissions WHERE id = ?)`,
        ).bind(submission.createdAt, submission.claimId, submission.submitter, submission.id),
        db.prepare(
            `UPDATE spent_nonces
                SET result_kind = 'bounty_submission'
              WHERE nonce = ? AND result_kind = 'bounty_submission_pending'
                AND EXISTS (SELECT 1 FROM bounty_submissions WHERE id = spent_nonces.result_id)`,
        ).bind(submission.nonceKey),
        db.prepare(
            `UPDATE spent_nonces SET result_kind = NULL, result_id = NULL
              WHERE nonce = ? AND result_kind = 'bounty_submission_pending'
                AND NOT EXISTS (SELECT 1 FROM bounty_submissions WHERE id = ?)`,
        ).bind(submission.nonceKey, submission.id),
        db.prepare("SELECT result_id AS id FROM spent_nonces WHERE nonce = ? AND result_kind = 'bounty_submission' AND result_id IS NOT NULL")
            .bind(submission.nonceKey),
    ]);
    return oneAllocatedId(results, "bounty submission did not allocate an id");
}

export async function insertBountyReview(db: D1Database, review: NewBountyReview): Promise<string> {
    const claimStatus = review.decision === "accepted" ? "accepted" : review.decision;
    const results = await db.batch([
        db.prepare("UPDATE spent_nonces SET result_kind = 'bounty_review_pending', result_id = ? WHERE nonce = ? AND result_kind IS NULL AND result_id IS NULL")
            .bind(review.id, review.nonceKey),
        db.prepare(
            `INSERT INTO bounty_reviews (id, submission_id, reviewer, created_at, decision, review_note, payment_verified_by_board, payment_state)
             SELECT ?, ?, ?, ?, ?, ?, 0, 'payment_unverified'
              WHERE EXISTS (SELECT 1 FROM spent_nonces WHERE nonce = ? AND result_kind = 'bounty_review_pending' AND result_id = ?)
                AND EXISTS (
                    SELECT 1
                      FROM bounty_submissions s
                      JOIN bounty_claims c ON c.id = s.claim_id
                      JOIN bounties b ON b.id = c.bounty_id
                     WHERE s.id = ? AND b.requester = ? AND s.status = 'pending_review'
                )`,
        ).bind(
            review.id,
            review.submissionId,
            review.reviewer,
            review.createdAt,
            review.decision,
            review.reviewNote,
            review.nonceKey,
            review.id,
            review.submissionId,
            review.reviewer,
        ),
        db.prepare(
            `UPDATE bounty_submissions
                SET status = ?, review_id = ?
              WHERE id = ? AND EXISTS (SELECT 1 FROM bounty_reviews WHERE id = ?)`,
        ).bind(review.decision, review.id, review.submissionId, review.id),
        db.prepare(
            `UPDATE bounty_claims
                SET status = ?, updated_at = ?
              WHERE id = (SELECT claim_id FROM bounty_submissions WHERE id = ?)
                AND EXISTS (SELECT 1 FROM bounty_reviews WHERE id = ?)`,
        ).bind(claimStatus, review.createdAt, review.submissionId, review.id),
        db.prepare(
            `UPDATE spent_nonces
                SET result_kind = 'bounty_review'
              WHERE nonce = ? AND result_kind = 'bounty_review_pending'
                AND EXISTS (SELECT 1 FROM bounty_reviews WHERE id = spent_nonces.result_id)`,
        ).bind(review.nonceKey),
        db.prepare(
            `UPDATE spent_nonces SET result_kind = NULL, result_id = NULL
              WHERE nonce = ? AND result_kind = 'bounty_review_pending'
                AND NOT EXISTS (SELECT 1 FROM bounty_reviews WHERE id = ?)`,
        ).bind(review.nonceKey, review.id),
        db.prepare("SELECT result_id AS id FROM spent_nonces WHERE nonce = ? AND result_kind = 'bounty_review' AND result_id IS NOT NULL")
            .bind(review.nonceKey),
    ]);
    return oneAllocatedId(results, "bounty review did not allocate an id");
}

function oneAllocatedId(results: D1Result[], message: string): string {
    const allocated = results[0]?.meta.changes ?? 0;
    const returned = results.at(-1) as D1Result<{ id: string }> | undefined;
    const id = returned?.results?.[0]?.id;
    if (allocated !== 1 || typeof id !== "string" || id.length === 0) {
        throw new Error(message);
    }
    return id;
}
