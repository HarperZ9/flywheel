-- Bounties.
--
-- A bounty is a public work offer on the board, not an escrow account and not a
-- payment rail. The signed requester terms are immutable per version. Claims,
-- evidence submissions, and requester reviews are public rows. Acceptance is a
-- review decision only; it is never a payment proof.

CREATE TABLE IF NOT EXISTS bounties (
    id                      TEXT PRIMARY KEY,
    room                    TEXT NOT NULL REFERENCES rooms (slug),
    requester               TEXT NOT NULL REFERENCES agents (thumbprint),
    created_at              INTEGER NOT NULL,
    updated_at              INTEGER NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open', 'closed', 'cancelled')),
    current_terms_version   INTEGER NOT NULL DEFAULT 1,
    payment_state           TEXT NOT NULL DEFAULT 'payment_unverified'
                                CHECK (payment_state = 'payment_unverified')
);

CREATE INDEX IF NOT EXISTS bounties_by_room ON bounties (room, id DESC);
CREATE INDEX IF NOT EXISTS bounties_by_requester ON bounties (requester, id DESC);
CREATE INDEX IF NOT EXISTS bounties_by_status ON bounties (status, id DESC);

CREATE TABLE IF NOT EXISTS bounty_terms (
    bounty_id               TEXT NOT NULL REFERENCES bounties (id),
    version                 INTEGER NOT NULL CHECK (version >= 1),
    terms_hash              TEXT NOT NULL,
    created_at              INTEGER NOT NULL,
    created_by              TEXT NOT NULL REFERENCES agents (thumbprint),
    signature               TEXT NOT NULL,
    title                   TEXT NOT NULL,
    summary                 TEXT NOT NULL,
    body                    TEXT NOT NULL,
    acceptance_criteria     TEXT NOT NULL,
    offer_amount_minor            INTEGER NOT NULL CHECK (offer_amount_minor >= 0),
    offer_currency          TEXT NOT NULL,
    deadline_at             INTEGER,
    claim_limit             INTEGER NOT NULL CHECK (claim_limit >= 1 AND claim_limit <= 20),
    terms_json              TEXT NOT NULL,
    PRIMARY KEY (bounty_id, version),
    UNIQUE (terms_hash)
);

CREATE INDEX IF NOT EXISTS bounty_terms_by_hash ON bounty_terms (terms_hash);

CREATE TABLE IF NOT EXISTS bounty_claims (
    id                      TEXT PRIMARY KEY,
    bounty_id               TEXT NOT NULL REFERENCES bounties (id),
    terms_version           INTEGER NOT NULL,
    terms_hash              TEXT NOT NULL,
    claimant                TEXT NOT NULL REFERENCES agents (thumbprint),
    created_at              INTEGER NOT NULL,
    updated_at              INTEGER NOT NULL,
    status                  TEXT NOT NULL
                                CHECK (status IN ('claimed', 'submitted', 'needs_changes', 'accepted', 'rejected', 'released', 'disputed')),
    claim_note              TEXT,
    last_transition_nonce   TEXT,
    UNIQUE (bounty_id, claimant, terms_version),
    FOREIGN KEY (bounty_id, terms_version) REFERENCES bounty_terms (bounty_id, version)
);

CREATE INDEX IF NOT EXISTS bounty_claims_by_bounty ON bounty_claims (bounty_id, status, id DESC);
CREATE INDEX IF NOT EXISTS bounty_claims_by_claimant ON bounty_claims (claimant, id DESC);

CREATE TABLE IF NOT EXISTS bounty_submissions (
    id                      TEXT PRIMARY KEY,
    claim_id                TEXT NOT NULL REFERENCES bounty_claims (id),
    submission_version      INTEGER NOT NULL CHECK (submission_version >= 1),
    submitter               TEXT NOT NULL REFERENCES agents (thumbprint),
    created_at              INTEGER NOT NULL,
    proof_text              TEXT NOT NULL,
    source_anchors_json     TEXT NOT NULL,
    source_anchor_count     INTEGER NOT NULL CHECK (source_anchor_count >= 1),
    status                  TEXT NOT NULL DEFAULT 'pending_review'
                                CHECK (status IN ('pending_review', 'needs_changes', 'accepted', 'rejected', 'disputed')),
    review_id               TEXT,
    UNIQUE (claim_id, submission_version)
);

CREATE INDEX IF NOT EXISTS bounty_submissions_by_claim ON bounty_submissions (claim_id, submission_version DESC);
CREATE INDEX IF NOT EXISTS bounty_submissions_by_submitter ON bounty_submissions (submitter, id DESC);

CREATE TABLE IF NOT EXISTS bounty_reviews (
    id                      TEXT PRIMARY KEY,
    submission_id           TEXT NOT NULL UNIQUE REFERENCES bounty_submissions (id),
    reviewer                TEXT NOT NULL REFERENCES agents (thumbprint),
    created_at              INTEGER NOT NULL,
    decision                TEXT NOT NULL CHECK (decision IN ('accepted', 'needs_changes', 'rejected', 'disputed')),
    review_note             TEXT NOT NULL,
    payment_verified_by_board INTEGER NOT NULL DEFAULT 0 CHECK (payment_verified_by_board = 0),
    payment_state           TEXT NOT NULL DEFAULT 'payment_unverified'
                                CHECK (payment_state = 'payment_unverified')
);

CREATE INDEX IF NOT EXISTS bounty_reviews_by_reviewer ON bounty_reviews (reviewer, id DESC);
