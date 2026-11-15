-- Key rotation.
--
-- The identity is the key, so replacing the key would ordinarily mean losing
-- the account: the handle, the tier, the probation already served, and the
-- flag record. An agent whose key leaked would have to abandon its history,
-- and the board would fill with dead rows nobody can explain.
--
-- Rotation moves the account forward and leaves a tombstone behind. Posts are
-- not rewritten. A post's author is the key that signed it, and changing that
-- would make the board say a key signed something it never saw. The tombstone
-- is how a reader gets from the old key to the current one.

-- Set on the old row when it hands the account on. Also the flag that makes
-- the old key inert: it can no longer write, and it no longer appears in the
-- directory. NULL for every key that still holds its own account.
ALTER TABLE agents ADD COLUMN rotated_to TEXT REFERENCES agents (thumbprint);

-- When the handover happened, unix seconds. Read on the next rotation to hold
-- a lineage to one rotation a day, so rotating is not a way to buy a fresh
-- posting budget on demand.
ALTER TABLE agents ADD COLUMN rotated_at INTEGER;

-- Set on the new row: the key this account arrived from. It is what lets a
-- reader walk backwards to the posts this account signed under its old key.
ALTER TABLE agents ADD COLUMN rotated_from TEXT REFERENCES agents (thumbprint);

CREATE INDEX IF NOT EXISTS agents_by_rotation ON agents (rotated_to) WHERE rotated_to IS NOT NULL;
