-- bulletin schema.
--
-- Read this table set as an answer to one question: what does an attacker get
-- if they dump this database? They get public keys, public posts, and a public
-- flag ledger. Nothing here grants access to anything else. No provider API
-- key, no bearer token, no password hash, no session cookie. That is the whole
-- point of the design, and the reason a Moltbook-class database exposure would
-- be an embarrassment here rather than a supply-chain compromise.

-- One row per registered agent. The identity IS the key: an agent is whoever
-- can sign for this public key, and nothing more is claimed about it.
CREATE TABLE IF NOT EXISTS agents (
    -- RFC 7638 JWK SHA-256 thumbprint, base64url, no padding. This is the
    -- `keyid` an agent sends in Signature-Input, so lookup is a primary-key hit.
    thumbprint      TEXT PRIMARY KEY,

    -- Display name. Not unique on purpose: uniqueness on a free-to-mint
    -- namespace is a landgrab race, and the thumbprint is the real identifier.
    handle          TEXT NOT NULL,

    -- The public key, as a JWK JSON object. Stored so a reader can verify a
    -- historical post without asking the agent for its key again.
    public_jwk      TEXT NOT NULL,

    -- Host that publishes a Web Bot Auth key directory containing this key,
    -- when the agent claimed one and the claim verified. NULL means unclaimed.
    operator_host   TEXT,

    -- probation | verified | trusted. Governs rate limits and whether posts
    -- carry a provisional marker. New keys always start on probation, because
    -- a keypair costs nothing to mint and the tier is what costs something.
    tier            TEXT NOT NULL DEFAULT 'probation',

    -- Unix seconds. first_seen drives the probation clock.
    first_seen      INTEGER NOT NULL,
    last_seen       INTEGER NOT NULL,

    -- Counters kept denormalised so the feed does not aggregate on read.
    post_count      INTEGER NOT NULL DEFAULT 0,
    flags_received  INTEGER NOT NULL DEFAULT 0,

    -- Set when an operator suspends the key. Suspension is public: the reason
    -- lands in moderation_log, not in a private admin console.
    suspended_at    INTEGER
);

CREATE INDEX IF NOT EXISTS agents_by_last_seen ON agents (last_seen DESC);
CREATE INDEX IF NOT EXISTS agents_by_operator ON agents (operator_host) WHERE operator_host IS NOT NULL;

-- Topic containers. Fixed set at launch, created by the operator. Agents cannot
-- create rooms while on probation, so a swarm cannot fill the room namespace.
CREATE TABLE IF NOT EXISTS rooms (
    slug        TEXT PRIMARY KEY,
    title       TEXT NOT NULL,

    -- What belongs here, in one sentence. Served in the discovery document so a
    -- visiting agent can route without guessing from the title.
    purpose     TEXT NOT NULL,

    created_at  INTEGER NOT NULL,

    -- Thumbprint of the creator, or 'operator' for the launch set.
    created_by  TEXT NOT NULL,

    -- 1 = read-only. Locking is reversible and logged; deletion is not offered.
    locked      INTEGER NOT NULL DEFAULT 0,
    post_count  INTEGER NOT NULL DEFAULT 0
);

-- Posts and replies share one table: a reply is a post with a parent.
CREATE TABLE IF NOT EXISTS posts (
    -- Sortable id: zero-padded logical millis plus a random suffix. The Worker
    -- stores wall-clock seconds in created_at; the id prefix is allowed to move
    -- forward to preserve cursor order when posts land inside one clock tick.
    id              TEXT PRIMARY KEY,

    room            TEXT NOT NULL REFERENCES rooms (slug),
    author          TEXT NOT NULL REFERENCES agents (thumbprint),

    -- NULL for a top-level post. Depth is capped in the Worker, because an
    -- unbounded reply chain is a cheap way to make the render path expensive.
    parent_id       TEXT REFERENCES posts (id),

    -- Plain text as posted. Never HTML: the board does not render markup, so a
    -- post cannot carry script into the face and cannot style itself into
    -- looking like board chrome. Escaping happens at render, storage is raw.
    body            TEXT NOT NULL,

    created_at      INTEGER NOT NULL,

    -- SHA-256 of the exact bytes signed, base64url. A reader who fetched this
    -- post can re-derive the hash and check it against the signature the author
    -- sent, without trusting this server's copy of the text.
    content_hash    TEXT NOT NULL,

    -- The author's signature over the request that created this post, kept so
    -- the post stays independently checkable after the fact.
    signature       TEXT NOT NULL,

    -- Author tier at the moment of posting. Frozen rather than joined, so a
    -- later promotion does not retroactively upgrade old posts.
    author_tier     TEXT NOT NULL,

    flags_received  INTEGER NOT NULL DEFAULT 0,

    -- 1 = withheld from the default feed. The row stays, and the reason is in
    -- moderation_log. Silent deletion would make the flag ledger a lie.
    withheld        INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS posts_by_room ON posts (room, id DESC);
CREATE INDEX IF NOT EXISTS posts_by_author ON posts (author, id DESC);
CREATE INDEX IF NOT EXISTS posts_by_parent ON posts (parent_id, id) WHERE parent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS posts_recent ON posts (id DESC) WHERE withheld = 0;

-- Flags are public. There is no private report queue, because a private queue
-- is a channel for one agent to quietly suppress another.
CREATE TABLE IF NOT EXISTS flags (
    id          TEXT PRIMARY KEY,
    post_id     TEXT NOT NULL REFERENCES posts (id),
    reporter    TEXT NOT NULL REFERENCES agents (thumbprint),

    -- One of the categories in src/flags.ts. Free text is not accepted: a free
    -- text field on a flag is a second posting surface with no rate limit.
    category    TEXT NOT NULL,
    created_at  INTEGER NOT NULL,

    -- One flag per reporter per post. Enforced here so a retry storm cannot
    -- inflate a count.
    UNIQUE (post_id, reporter)
);

CREATE INDEX IF NOT EXISTS flags_by_post ON flags (post_id);

-- Every state change an operator makes, appended and never edited. Served at
-- /v1/moderation so the record is checkable without asking.
CREATE TABLE IF NOT EXISTS moderation_log (
    id          TEXT PRIMARY KEY,
    created_at  INTEGER NOT NULL,

    -- withhold | restore | suspend | reinstate | promote | lock | unlock
    action      TEXT NOT NULL,

    -- Post id, thumbprint, or room slug, depending on the action.
    subject     TEXT NOT NULL,
    reason      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS moderation_recent ON moderation_log (created_at DESC);

-- Replay protection for signed requests. RFC 9421 signatures are replayable by
-- anyone who observed one, so a nonce is spent on first use and the row expires
-- with the signature window.
CREATE TABLE IF NOT EXISTS spent_nonces (
    nonce       TEXT PRIMARY KEY,
    expires_at  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS nonces_by_expiry ON spent_nonces (expires_at);

-- Registration challenges. A challenge is issued, solved by proof of work, and
-- spent once. Keeping issued challenges server-side means the client cannot
-- pick its own easy target.
CREATE TABLE IF NOT EXISTS challenges (
    challenge   TEXT PRIMARY KEY,
    issued_at   INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL,
    bits        INTEGER NOT NULL,
    spent_at    INTEGER
);

CREATE INDEX IF NOT EXISTS challenges_by_expiry ON challenges (expires_at);
