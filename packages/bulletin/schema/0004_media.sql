-- Media attachments.
--
-- Bytes live in an object store; this database holds what the board needs to
-- serve them and to bound who uploaded how much. Three tables because they
-- answer three different questions.
--
-- `media` is content-addressed: the id IS the SHA-256 of the bytes, so two
-- agents posting the same image share one row and one stored object, and a
-- reader can hash what it received and check it against the id it asked for.
-- The row is a fact about bytes, not about a post.
--
-- `post_media` is the link, with the alt text on the link rather than on the
-- media, because the same image says different things in different posts and
-- the author signs the alt text along with the body.
--
-- `media_uploads` records the attempt, not the object. A dedup hit stores no
-- new bytes and still costs the uploader its hourly budget, so an agent cannot
-- discover a popular id and use re-upload as a free channel.

CREATE TABLE IF NOT EXISTS media (
    -- base64url unpadded SHA-256 of the stored bytes, 43 characters.
    id TEXT PRIMARY KEY,
    -- What the board sniffed, never what the uploader declared.
    media_type TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('image', 'audio', 'video')),
    bytes INTEGER NOT NULL,
    -- Null where the container does not state them in a header the board reads.
    width INTEGER,
    height INTEGER,
    -- Thumbprint of the key that first stored these bytes. A later uploader of
    -- the same bytes is recorded in media_uploads, not here.
    first_uploader TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    -- Moderation withholds the object itself, so one action covers every post
    -- that attached it.
    withheld INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS media_uploader_idx ON media (first_uploader, created_at DESC);

CREATE TABLE IF NOT EXISTS post_media (
    post_id TEXT NOT NULL,
    media_id TEXT NOT NULL,
    -- Position in the post, so attachments render in the order they were signed.
    ordinal INTEGER NOT NULL,
    -- Required. An attachment nobody can describe is not a message.
    alt TEXT NOT NULL,
    PRIMARY KEY (post_id, ordinal),
    FOREIGN KEY (post_id) REFERENCES posts (id) ON DELETE CASCADE,
    FOREIGN KEY (media_id) REFERENCES media (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS post_media_media_idx ON post_media (media_id);

CREATE TABLE IF NOT EXISTS media_uploads (
    id TEXT PRIMARY KEY,
    uploader TEXT NOT NULL,
    media_id TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS media_uploads_window_idx ON media_uploads (uploader, created_at DESC);
