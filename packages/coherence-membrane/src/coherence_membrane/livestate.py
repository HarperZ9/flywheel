"""L0 live-state -- a witnessed, replayable diff-chain over a Field stream.

Reconstruct and re-verify the substrate at any past tick from a chain you did not
author; resume it from disk without trusting the file. Stdlib only. Inert and
advisory: it records and re-derives; it grants no authority, mutates no subject.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path

from .field import Field, FieldKind
from .observation import sha256_hex
from .phash import MATCH, DRIFT, UNVERIFIABLE
from .lattice import DRIFT_LATTICE

CANON_ALGO = b"field-sha256-canonical-v1"


class ChainLoadError(ValueError):
    """A manifest that cannot be safely re-derived (structural malformation)."""


def field_canonical_bytes(f: Field) -> bytes:
    """Deterministic identity payload. Unknown cells are forced to 0.0 so the
    identity is (known content + uncertainty shape), never garbage under the mask."""
    n = f.width * f.height
    mask = bytearray((n + 7) // 8)
    for i, u in enumerate(f.unknown):
        if u:
            mask[i >> 3] |= 1 << (i & 7)
    parts = [CANON_ALGO, b"\n", f.kind.value.encode("ascii"),
             struct.pack(">II", f.width, f.height), bytes(mask)]
    for v, u in zip(f.values, f.unknown):
        parts.append(struct.pack(">d", 0.0 if u else float(v)))
    return b"".join(parts)


def field_state_sha(f: Field) -> str:
    return sha256_hex(field_canonical_bytes(f))


@dataclass(frozen=True)
class FieldSnapshot:
    """A full Field at a tick + its content hash. `verdict` is the snapshot's trust
    level (MATCH normally; UNVERIFIABLE for a throttled tick or a failed reconstruct)."""
    field: Field
    state_sha: str
    tick: int
    verdict: str = MATCH
    reason: str = ""


def field_diff(parent: Field, new: Field):
    """Sparse moved-cell diff + the tick verdict (DRIFT_LATTICE fold_meet)."""
    changes = []
    verdicts = []
    for i in range(len(parent.values)):
        au, bu = parent.unknown[i], new.unknown[i]
        moved = (au != bu) or (not au and not bu and parent.values[i] != new.values[i])
        if not moved:
            continue
        changes.append((i, 0.0 if bu else float(new.values[i]), bu))
        verdicts.append(UNVERIFIABLE if (bu and not au) else DRIFT)  # known->unknown lost; else change
    return changes, DRIFT_LATTICE.fold_meet(verdicts)  # empty -> MATCH (top)


def field_apply(parent: Field, changes) -> Field:
    """Apply a sparse change list to a Field, returning a new Field (same dims)."""
    values = list(parent.values)
    unknown = list(parent.unknown)
    for (i, nv, nu) in changes:
        values[i] = 0.0 if nu else float(nv)
        unknown[i] = bool(nu)
    return Field(parent.width, parent.height, parent.kind, tuple(values), tuple(unknown))


@dataclass(frozen=True)
class FieldDiff:
    parent_sha: str
    result_sha: str
    changes: tuple          # tuple of (index, new_value, new_unknown)
    verdict: str
    tick: int
    throttle_reason: str | None = None


@dataclass(frozen=True)
class ChainVerdict:
    verdict: str
    reason: str
    broken_entry: int | None = None


def _field_to_dict(f: Field) -> dict:
    return {"w": f.width, "h": f.height, "kind": f.kind.value,
            "values": list(f.values), "unknown": [bool(u) for u in f.unknown]}


def _field_from_dict(d: dict) -> Field:
    return Field(int(d["w"]), int(d["h"]), FieldKind(d["kind"]),
                 tuple(float(v) for v in d["values"]), tuple(bool(u) for u in d["unknown"]))


class DiffChain:
    """A witnessed, replayable record of a Field stream over time."""

    def __init__(self, base: FieldSnapshot, *, subject: str, checkpoint_interval: int = 64):
        self.subject = subject
        self.checkpoint_interval = checkpoint_interval
        self.kind = base.field.kind
        self.entries: list = [base]   # entries[0] = base keyframe
        self._current: FieldSnapshot = base

    @classmethod
    def from_base(cls, field: Field, *, subject: str, checkpoint_interval: int = 64) -> "DiffChain":
        snap = FieldSnapshot(field, field_state_sha(field), 0)
        return cls(snap, subject=subject, checkpoint_interval=checkpoint_interval)

    @property
    def tick(self) -> int:
        return len(self.entries) - 1

    def current(self) -> FieldSnapshot:
        return self._current

    def append(self, field: "Field | None" = None, *, throttle_reason: str | None = None) -> FieldDiff:
        """Perceive the next state. throttle_reason (field ignored) -> whole-field-unknown
        keyframe (no silent gap). A differently-shaped field -> re-anchor keyframe."""
        if field is None and throttle_reason is None:
            raise ValueError("append requires a field or a throttle_reason")
        new_tick = self.tick + 1
        parent = self._current

        if throttle_reason is not None:
            pf = parent.field
            unknown_field = Field(pf.width, pf.height, pf.kind,
                                  tuple(0.0 for _ in pf.values), tuple(True for _ in pf.values))
            snap = FieldSnapshot(unknown_field, field_state_sha(unknown_field), new_tick,
                                 UNVERIFIABLE, throttle_reason)
            self.entries.append(snap)        # keyframe anchor; recovery is a clean keyframe too
            self._current = snap
            return FieldDiff(parent.state_sha, snap.state_sha, (), UNVERIFIABLE, new_tick, throttle_reason)

        if (field.width, field.height) != (parent.field.width, parent.field.height):
            snap = FieldSnapshot(field, field_state_sha(field), new_tick)
            self.entries.append(snap)        # re-anchor: a diff requires equal dims
            self._current = snap
            return FieldDiff(parent.state_sha, snap.state_sha, (), DRIFT, new_tick)

        changes, verdict = field_diff(parent.field, field)
        snap = FieldSnapshot(field, field_state_sha(field), new_tick)
        diff = FieldDiff(parent.state_sha, snap.state_sha, tuple(changes), verdict, new_tick)
        if self.checkpoint_interval and new_tick % self.checkpoint_interval == 0:
            self.entries.append(snap)
        else:
            self.entries.append(diff)
        self._current = snap
        return diff

    def checkpoint(self) -> FieldSnapshot:
        """Force the current tick's entry to be a full keyframe."""
        self.entries[self.tick] = self._current
        return self._current

    def reconstruct(self, tick: int) -> FieldSnapshot:
        """Rebuild the state at `tick`: nearest keyframe <= tick, apply diffs, re-hash."""
        if tick < 0 or tick > self.tick:
            return FieldSnapshot(self._current.field, "", tick, UNVERIFIABLE,
                                 f"tick {tick} out of range [0,{self.tick}]")
        j = tick
        while j > 0 and not isinstance(self.entries[j], FieldSnapshot):
            j -= 1
        kf: FieldSnapshot = self.entries[j]
        state = kf.field
        if field_state_sha(state) != kf.state_sha:
            return FieldSnapshot(state, "", tick, UNVERIFIABLE, f"keyframe at {j} failed re-hash")
        for i in range(j + 1, tick + 1):
            e = self.entries[i]
            if isinstance(e, FieldSnapshot):
                state = e.field
                expect = e.state_sha
            else:
                state = field_apply(state, e.changes)
                expect = e.result_sha
            if field_state_sha(state) != expect:
                return FieldSnapshot(state, "", tick, UNVERIFIABLE, f"entry at {i} failed re-hash")
        target = self.entries[tick]
        v = target.verdict if isinstance(target, FieldSnapshot) else MATCH
        reason = target.reason if isinstance(target, FieldSnapshot) else ""
        return FieldSnapshot(state, field_state_sha(state), tick, v, reason)

    def verify(self) -> ChainVerdict:
        """Replay from base, re-hash every entry, confirm all parent->result links."""
        base = self.entries[0]
        if not isinstance(base, FieldSnapshot) or field_state_sha(base.field) != base.state_sha:
            return ChainVerdict(UNVERIFIABLE, "base keyframe failed re-hash", 0)
        if base.tick != 0:
            return ChainVerdict(UNVERIFIABLE, "base tick != 0", 0)
        prev_sha = base.state_sha
        state = base.field
        for i in range(1, len(self.entries)):
            e = self.entries[i]
            if e.tick != i:
                return ChainVerdict(UNVERIFIABLE, f"entry {i} claims tick {e.tick} (inserted/reordered)", i)
            if isinstance(e, FieldSnapshot):
                if field_state_sha(e.field) != e.state_sha:
                    return ChainVerdict(UNVERIFIABLE, f"keyframe {i} failed re-hash", i)
                state, prev_sha = e.field, e.state_sha
            else:  # FieldDiff
                if e.parent_sha != prev_sha:
                    return ChainVerdict(UNVERIFIABLE, f"diff {i} parent_sha breaks the chain", i)
                state = field_apply(state, e.changes)
                if field_state_sha(state) != e.result_sha:
                    return ChainVerdict(UNVERIFIABLE, f"diff {i} result_sha != re-derived state", i)
                prev_sha = e.result_sha
        return ChainVerdict(MATCH, "chain intact", None)

    def _entry_to_dict(self, e) -> dict:
        if isinstance(e, FieldSnapshot):
            return {"kind": "keyframe", "field": _field_to_dict(e.field),
                    "state_sha": e.state_sha, "tick": e.tick,
                    "verdict": e.verdict, "reason": e.reason}
        return {"kind": "diff", "parent_sha": e.parent_sha, "result_sha": e.result_sha,
                "changes": [list(c) for c in e.changes], "verdict": e.verdict,
                "tick": e.tick, "throttle_reason": e.throttle_reason}

    def save(self, path) -> None:
        data = {"subject": self.subject, "checkpoint_interval": self.checkpoint_interval,
                "entries": [self._entry_to_dict(e) for e in self.entries],
                "n_entries": len(self.entries), "head_sha": self._current.state_sha}
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "DiffChain":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            raw = data["entries"]
            if not raw or raw[0].get("kind") != "keyframe":
                raise ChainLoadError("manifest must start with a keyframe entry")
            entries: list = []
            for d in raw:
                kind = d["kind"]
                if kind == "keyframe":
                    f = _field_from_dict(d["field"])
                    entries.append(FieldSnapshot(f, str(d["state_sha"]), int(d["tick"]),
                                                 str(d.get("verdict", MATCH)), str(d.get("reason", ""))))
                elif kind == "diff":
                    changes = tuple(tuple(c) for c in d["changes"])
                    if any(len(c) != 3 for c in changes):
                        raise ChainLoadError("diff change rows must have arity 3")
                    entries.append(FieldDiff(str(d["parent_sha"]), str(d["result_sha"]), changes,
                                             str(d["verdict"]), int(d["tick"]), d.get("throttle_reason")))
                else:
                    raise ChainLoadError(f"unknown entry kind {kind!r}")
            n = data.get("n_entries")
            if n is not None and int(n) != len(entries):
                raise ChainLoadError(f"entry count {len(entries)} != n_entries {n} (truncated/inserted)")
            chain = cls(entries[0], subject=str(data["subject"]),
                        checkpoint_interval=int(data["checkpoint_interval"]))
            chain.entries = entries
            last = entries[-1]
            chain._current = last if isinstance(last, FieldSnapshot) else chain.reconstruct(len(entries) - 1)
            head = data.get("head_sha")
            if head is not None and chain._current.state_sha != str(head):
                raise ChainLoadError("head_sha mismatch -- chain truncated or altered")
            return chain
        except ChainLoadError:
            raise
        except (KeyError, ValueError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ChainLoadError(f"malformed manifest: {exc!r}") from exc
