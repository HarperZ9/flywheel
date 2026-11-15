"""test_reconcile.py -- V4: the reconcile decision lattice and its per-surface leg.

The reconcile loop decides, per managed surface, whether a byte-drift is a safe
mechanical fast-forward or a conflict a human must adjudicate. The discriminator
is the V3→V4 hard edge: the decision consumes the external crucible persona drift
verdict, not a self-report. A byte-drift whose scope carries a persona whose basis
is no longer sound is a conflict; a byte-drift with a sound (or absent) persona
basis is a fast-forward.

These tests cover the pure pieces in isolation:
- persona_fold lifts V3's single-persona fold (D-46) to a set of personas.
- classify is the pure lattice over (surface-drift verdict, persona fold).
- _contributing_personas selects the personas whose scope gates a surface,
  mirroring the render contribution (pool_for plus scope containment).
- classify_surface integrates the drift check, the persona health, and the gate
  overlay into one per-surface verdict, with all IO and the assessor injected.
"""
from __future__ import annotations

import os

from canon.drift import (
    VERDICT_DRIFT,
    VERDICT_MATCH,
    VERDICT_MISSING,
    VERDICT_OFF_LIMITS,
    VERDICT_REFUSED,
)
from canon.persona_thesis import DRIFT, MATCH, UNVERIFIABLE, DriftVerdict
from canon.reconcile import (
    CONFLICT,
    FAST_FORWARD,
    FOLD_NONE,
    HELD,
    IN_SYNC,
    OVERRIDDEN,
    REFUSED,
    SKIP_MISSING,
    SKIP_OFF_LIMITS,
    SurfaceReconcile,
    classify,
    classify_surface,
    contributing_personas,
    persona_fold,
    persona_health,
)
from canon.reconcile_gate import (
    APPROVED,
    EDITED,
    ON_EXPIRY_APPROVE,
    ON_EXPIRY_REJECT,
    PENDING,
    REJECTED,
)
from canon.registry import (
    SURFACE_CATALOG,
    resolve_surface_path,
    write_surface,
)
from canon.schema import (
    KIND_EPISODIC_MEMORY,
    KIND_PERSONALITY_BLOCK,
    KIND_SYNTHESIZED_PERSONA_L3,
    Provenance,
    Record,
    Temporal,
)

HOME = os.path.join("fake", "home")
WS = os.path.join("fake", "ws")


def _dv(verdict: str, persona_id: str = "persona-x") -> DriftVerdict:
    """A DriftVerdict carrying only the headline the fold reads."""
    return DriftVerdict(persona_id=persona_id, verdict=verdict,
                        match=0, drift=0, unverifiable=0)


def _persona(id: str, scope: str, source_ids=()) -> Record:
    prov = Provenance(harness="mneme", source_hash="c" * 64, create_ord=205)
    return Record(kind=KIND_SYNTHESIZED_PERSONA_L3, id=id, scope=scope,
                  data={"layer": "L3", "text": "A faithful summary.",
                        "source_ids": list(source_ids)},
                  provenance=prov,
                  temporal=Temporal(valid_until=None, supersedes=None))


def _source(id: str, *, scope: str = "global", supersedes=None,
            ord: int = 100) -> Record:
    prov = Provenance(harness="mneme", source_hash="a" * 64, create_ord=ord)
    return Record(kind=KIND_EPISODIC_MEMORY, id=id, scope=scope,
                  data={"layer": "L1", "text": f"memory {id}", "source_ids": []},
                  provenance=prov,
                  temporal=Temporal(valid_until=None, supersedes=supersedes))


def _ladder_assessor():
    """A fake crucible assessor mirroring the honesty ladder over the two basis
    claims: an unmeasured axis (deviation None) is unverifiable, a deviation
    within tolerance is a match, and a deviation past tolerance is drift. Driven
    by canon's real measurements, so the pool shape decides the verdict."""
    def assess(payload):
        match = drift = unverifiable = 0
        for claim in payload["claims"]:
            deviation = claim["deviation"]
            if deviation is None:
                unverifiable += 1
            elif deviation <= claim["tolerance"]:
                match += 1
            else:
                drift += 1
        return {"match": match, "drift": drift, "unverifiable": unverifiable}
    return assess


def _block(id: str, scope: str) -> Record:
    prov = Provenance(harness="claude-code", source_hash="a" * 64, create_ord=10)
    return Record(kind=KIND_PERSONALITY_BLOCK, id=id, scope=scope,
                  data={"heading": id, "body": f"block {id}"},
                  provenance=prov,
                  temporal=Temporal(valid_until=None, supersedes=None))


def _surface(harness: str, scope: str):
    for s in SURFACE_CATALOG:
        if s.harness == harness and s.scope == scope:
            return s
    raise KeyError((harness, scope))


def _ids(records) -> set:
    return {r.id for r in records}


# -- persona_fold: D-46 lifted to a set of personas -----------------------

def test_no_personas_folds_to_none():
    assert persona_fold([]) == FOLD_NONE


def test_all_match_folds_to_match():
    assert persona_fold([_dv(MATCH), _dv(MATCH)]) == MATCH


def test_any_unverifiable_folds_to_unverifiable():
    assert persona_fold([_dv(MATCH), _dv(UNVERIFIABLE)]) == UNVERIFIABLE


def test_any_drift_folds_to_drift():
    assert persona_fold([_dv(MATCH), _dv(DRIFT)]) == DRIFT


def test_drift_outranks_unverifiable_across_personas():
    # A proven drift on one persona is not softened by an honest null on another,
    # the same order D-46 folds the two axes of a single persona.
    assert persona_fold([_dv(UNVERIFIABLE), _dv(DRIFT)]) == DRIFT


# -- classify: the pure lattice -------------------------------------------

def test_a_matching_surface_is_in_sync_whatever_the_persona():
    # An in-sync surface has no write decision to make, so the persona verdict
    # rides along in the report but never changes the classification. canon
    # cannot re-synthesize a persona from a catalog reconcile anyway.
    for fold in (FOLD_NONE, MATCH, UNVERIFIABLE, DRIFT):
        assert classify(VERDICT_MATCH, fold) == IN_SYNC


def test_a_drift_with_no_persona_basis_is_a_fast_forward():
    assert classify(VERDICT_DRIFT, FOLD_NONE) == FAST_FORWARD


def test_a_drift_with_a_sound_persona_is_a_fast_forward():
    assert classify(VERDICT_DRIFT, MATCH) == FAST_FORWARD


def test_a_drift_with_an_unverifiable_persona_is_held():
    # An honest null on the basis is not proof of drift, but it is not a clean
    # fast-forward either: hold it for a human, distinct from a proven conflict.
    assert classify(VERDICT_DRIFT, UNVERIFIABLE) == HELD


def test_a_drift_with_a_drifted_persona_is_a_conflict():
    # The hard edge: a byte-drift whose scope carries a persona whose basis
    # eroded is a conflict, not a fast-forward.
    assert classify(VERDICT_DRIFT, DRIFT) == CONFLICT


def test_off_limits_and_missing_are_benign_skips():
    for fold in (FOLD_NONE, MATCH, DRIFT):
        assert classify(VERDICT_OFF_LIMITS, fold) == SKIP_OFF_LIMITS
        assert classify(VERDICT_MISSING, fold) == SKIP_MISSING


def test_a_refused_surface_is_refused_never_gated():
    for fold in (FOLD_NONE, MATCH, DRIFT):
        assert classify(VERDICT_REFUSED, fold) == REFUSED


def test_an_unknown_drift_verdict_fails_closed_to_refused():
    # classify is total. A verdict outside drift.py's closed vocabulary is a
    # wiring fault; it fails closed to REFUSED (reported, never written, never a
    # spurious human gate), never to a write.
    assert classify("some-new-verdict", MATCH) == REFUSED


def test_an_unknown_persona_fold_fails_closed_to_refused():
    assert classify(VERDICT_DRIFT, "some-new-fold") == REFUSED


# -- contributing_personas: the scope coupling the hard edge rides on -----

# A pool with a persona and a personality-block at each scope. The block records
# must never appear in a persona selection whatever the surface.
_GP, _WP = _persona("gp", "global"), _persona("wp", "workspace")
_GB, _WB = _block("gb", "global"), _block("wb", "workspace")
_MIXED_POOL = [_GP, _WP, _GB, _WB]


def test_a_global_surface_contributes_only_global_personas():
    # A global surface renders only global blocks (layering), so only a global
    # persona's basis underlies its bytes.
    surface = _surface("claude-code", "global")
    assert _ids(contributing_personas(surface, _MIXED_POOL)) == {"gp"}


def test_a_workspace_surface_with_a_global_sibling_contributes_only_workspace():
    # claude-code splits global into .claude/CLAUDE.md, so the workspace CLAUDE.md
    # carries only workspace-authored blocks; the globals' basis is the sibling
    # file's concern. This mirrors pool_for's authored-split exactly.
    surface = _surface("claude-code", "workspace")
    assert _ids(contributing_personas(surface, _MIXED_POOL)) == {"wp"}


def test_a_lone_workspace_surface_contributes_both_scopes():
    # codex has no global sibling, so AGENTS.md renders the full merged set; its
    # basis spans global and workspace personas.
    surface = _surface("codex", "workspace")
    assert _ids(contributing_personas(surface, _MIXED_POOL)) == {"gp", "wp"}


def test_the_soul_surface_also_contributes_both_scopes():
    surface = _surface("hermes", "workspace")
    assert _ids(contributing_personas(surface, _MIXED_POOL)) == {"gp", "wp"}


def test_personality_blocks_are_never_contributing_personas():
    # A pool of only personality-blocks yields no personas for any surface: the
    # health leg measures the synthesis kind alone.
    blocks = [_block("b1", "global"), _block("b2", "workspace")]
    for surface in SURFACE_CATALOG:
        assert contributing_personas(surface, blocks) == []


# -- persona_health: run the injected assessor over the gating personas ---

def test_health_returns_one_verdict_per_contributing_persona():
    gp = _persona("gp", "global", source_ids=["s1"])
    pool = [gp, _source("s1", scope="global")]
    surface = _surface("claude-code", "global")
    verdicts = persona_health(surface, pool, assess=_ladder_assessor())
    assert [v.persona_id for v in verdicts] == ["gp"]
    assert verdicts[0].verdict == MATCH


def test_health_is_empty_when_no_persona_gates_the_surface():
    # A workspace-only persona does not gate a global surface, so the health leg
    # measures nothing and folds (elsewhere) to NONE, not a fabricated MATCH.
    pool = [_persona("wp", "workspace", source_ids=["s1"]),
            _source("s1", scope="workspace")]
    surface = _surface("claude-code", "global")
    assert persona_health(surface, pool, assess=_ladder_assessor()) == []


def test_health_resolves_the_basis_against_the_whole_pool():
    # A global persona whose source lives at workspace scope: the basis check must
    # see the whole pool, not the scope-filtered gating subset. If health passed
    # the filtered candidates as the basis pool, the workspace source would read
    # absent and the verdict would be a false DRIFT.
    gp = _persona("gp", "global", source_ids=["s-work"])
    pool = [gp, _source("s-work", scope="workspace")]
    surface = _surface("claude-code", "global")
    verdicts = persona_health(surface, pool, assess=_ladder_assessor())
    assert verdicts[0].verdict == MATCH


def test_health_surfaces_a_real_drift_from_a_superseded_basis():
    # A source present but superseded by a newer record falsifies basis-current,
    # so the verdict flows through as DRIFT, not a hardcoded MATCH.
    gp = _persona("gp", "global", source_ids=["s1"])
    pool = [gp, _source("s1", scope="global"),
            _source("s1-new", scope="global", supersedes="s1", ord=300)]
    surface = _surface("claude-code", "global")
    verdicts = persona_health(surface, pool, assess=_ladder_assessor())
    assert verdicts[0].verdict == DRIFT


# -- classify_surface: the per-surface leg over real host bytes -----------
#
# classify_surface runs the drift check against a real host region, then folds
# the crucible persona verdict in only where it changes the write decision, then
# overlays any raised gate. All IO (read_text), the assessor, the gate reader,
# and the clock are injected, so no real file or engine is touched.

class _FakeFS:
    def __init__(self, files):
        self.files = dict(files)
        self.writes = []

    def read_text(self, path):
        return self.files.get(path)  # None for an absent file

    def write_text(self, path, text):
        self.files[path] = text
        self.writes.append(path)


def _host(scope: str) -> str:
    return (
        "intro\n"
        f"<!-- canon:begin scope={scope} -->\n"
        "<!-- canon:end -->\n"
        "outro\n"
    )


def _rblock(id: str, scope: str, body: str, ord: int = 20) -> Record:
    """A personality-block the R0 grammar can render into a surface region."""
    prov = Provenance(harness="claude-code", source_hash="a" * 64, create_ord=ord)
    return Record(kind=KIND_PERSONALITY_BLOCK, id=id, scope=scope,
                  data={"title": id.title(), "body": body}, provenance=prov)


_WBLK = _rblock("tone", "workspace", "W tone")


def _rendered(surface, blocks):
    """A FakeFS whose surface file already holds the clean rendered blocks."""
    path = resolve_surface_path(surface, home=HOME, workspace=WS)
    fs = _FakeFS({path: _host(surface.scope)})
    write_surface(surface, blocks, home=HOME, workspace=WS,
                  read_text=fs.read_text, write_text=fs.write_text)
    return path, fs


def _drift(fs, path):
    """Hand-edit the region interior so the surface byte-drifts from the pool."""
    fs.files[path] = fs.files[path].replace(
        "<!-- canon:end -->", "drifted line\n<!-- canon:end -->")


def _counting_assessor():
    inner = _ladder_assessor()
    calls = []

    def assess(payload):
        calls.append(payload)
        return inner(payload)

    assess.calls = calls
    return assess


def _gate_none():
    calls = []

    def gate_read(key):
        calls.append(key)
        return None

    gate_read.calls = calls
    return gate_read


def _gate_reply(reply):
    calls = []

    def gate_read(key):
        calls.append(key)
        return reply

    gate_read.calls = calls
    return gate_read


def _classify(surface, pool, fs, *, assess=None, gate_read=None, now=0):
    return classify_surface(
        surface, pool, home=HOME, workspace=WS, read_text=fs.read_text,
        assess=assess if assess is not None else _counting_assessor(),
        gate_read=gate_read if gate_read is not None else _gate_none(),
        now=now)


_CLAUDE_WS = _surface("claude-code", "workspace")


# -- a clean surface is in-sync and never touches the assessor or gate ----

def test_a_clean_surface_is_in_sync():
    path, fs = _rendered(_CLAUDE_WS, [_WBLK])
    assess, gate = _counting_assessor(), _gate_none()
    sr = _classify(_CLAUDE_WS, [_WBLK], fs, assess=assess, gate_read=gate)
    assert isinstance(sr, SurfaceReconcile)
    assert sr.classification == IN_SYNC
    assert sr.drift == VERDICT_MATCH
    assert sr.path == path
    assert sr.needs_gate is False
    assert sr.resolution is None


def test_a_clean_surface_never_runs_the_assessor_or_reads_a_gate():
    # The crucible verdict is consumed only at the fast-forward-vs-conflict fork,
    # which an in-sync surface never reaches: no drift, no basis measurement, no
    # gate lookup. The assessor may be a real engine, so this is cost-honest.
    _, fs = _rendered(_CLAUDE_WS, [_WBLK])
    assess, gate = _counting_assessor(), _gate_none()
    sr = _classify(_CLAUDE_WS, [_WBLK], fs, assess=assess, gate_read=gate)
    assert sr.personas == ()
    assert sr.persona_fold == FOLD_NONE
    assert assess.calls == []
    assert gate.calls == []


# -- a byte-drift with no or sound basis fast-forwards --------------------

def test_a_drift_with_no_persona_basis_fast_forwards():
    path, fs = _rendered(_CLAUDE_WS, [_WBLK])
    _drift(fs, path)
    sr = _classify(_CLAUDE_WS, [_WBLK], fs)
    assert sr.drift == VERDICT_DRIFT
    assert sr.persona_fold == FOLD_NONE
    assert sr.classification == FAST_FORWARD
    assert sr.needs_gate is False


def test_a_drift_with_a_sound_persona_fast_forwards():
    path, fs = _rendered(_CLAUDE_WS, [_WBLK])
    _drift(fs, path)
    wp = _persona("wp", "workspace", source_ids=["s1"])
    pool = [_WBLK, wp, _source("s1", scope="workspace")]
    assess = _counting_assessor()
    sr = _classify(_CLAUDE_WS, pool, fs, assess=assess)
    assert sr.drift == VERDICT_DRIFT
    assert [v.verdict for v in sr.personas] == [MATCH]
    assert sr.persona_fold == MATCH
    assert sr.classification == FAST_FORWARD
    assert sr.needs_gate is False
    assert len(assess.calls) == 1  # the assessor fired exactly once, on drift


# -- a byte-drift with an eroded basis is a conflict a human must gate ----

def test_a_drift_with_a_drifted_persona_and_no_gate_is_a_conflict():
    # The V3->V4 hard edge: the fast-forward-vs-conflict call consumes the
    # external crucible drift verdict. A superseded basis reads DRIFT, so the
    # byte-drift is a conflict, and with no gate raised yet the commit phase must
    # raise one.
    path, fs = _rendered(_CLAUDE_WS, [_WBLK])
    _drift(fs, path)
    wp = _persona("wp", "workspace", source_ids=["s1"])
    pool = [_WBLK, wp, _source("s1", scope="workspace"),
            _source("s1-new", scope="workspace", supersedes="s1", ord=300)]
    gate = _gate_none()
    sr = _classify(_CLAUDE_WS, pool, fs, gate_read=gate)
    assert sr.persona_fold == DRIFT
    assert sr.classification == CONFLICT
    assert sr.needs_gate is True
    assert sr.resolution is None
    assert gate.calls == [{"harness": "claude-code", "scope": "workspace",
                           "path": "CLAUDE.md"}]


def test_a_drift_with_an_unverifiable_persona_and_no_gate_is_held():
    # An empty basis cannot be measured, so the persona reads UNVERIFIABLE: not a
    # clean fast-forward, not a proven conflict. Hold it for a human, and with no
    # gate yet the commit phase raises one.
    path, fs = _rendered(_CLAUDE_WS, [_WBLK])
    _drift(fs, path)
    wp = _persona("wp", "workspace", source_ids=[])
    pool = [_WBLK, wp]
    gate = _gate_none()
    sr = _classify(_CLAUDE_WS, pool, fs, gate_read=gate)
    assert sr.persona_fold == UNVERIFIABLE
    assert sr.classification == HELD
    assert sr.needs_gate is True


# -- a raised gate overlays the conflict on resume ------------------------

def _conflict_pool():
    wp = _persona("wp", "workspace", source_ids=["s1"])
    return [_WBLK, wp, _source("s1", scope="workspace"),
            _source("s1-new", scope="workspace", supersedes="s1", ord=300)]


def test_an_approved_gate_overrides_a_conflict_to_a_write():
    path, fs = _rendered(_CLAUDE_WS, [_WBLK])
    _drift(fs, path)
    gate = _gate_reply({"resolution": APPROVED, "deadline": None,
                        "on_expiry": ON_EXPIRY_REJECT})
    sr = _classify(_CLAUDE_WS, _conflict_pool(), fs, gate_read=gate)
    assert sr.classification == OVERRIDDEN
    assert sr.needs_gate is False
    assert sr.resolution == APPROVED


def test_a_pending_gate_leaves_the_conflict_and_never_re_raises():
    # A gate already exists (gate_read replied), so needs_gate is False even
    # though the resolution holds: the commit phase must not raise a second gate.
    path, fs = _rendered(_CLAUDE_WS, [_WBLK])
    _drift(fs, path)
    gate = _gate_reply({"resolution": PENDING, "deadline": None,
                        "on_expiry": ON_EXPIRY_REJECT})
    sr = _classify(_CLAUDE_WS, _conflict_pool(), fs, gate_read=gate)
    assert sr.classification == CONFLICT
    assert sr.needs_gate is False
    assert sr.resolution == PENDING


def test_an_edited_gate_holds_the_conflict():
    # An edited resolution is a decision, but not an approval: it holds, it does
    # not write, and it never re-raises.
    path, fs = _rendered(_CLAUDE_WS, [_WBLK])
    _drift(fs, path)
    gate = _gate_reply({"resolution": EDITED, "deadline": None,
                        "on_expiry": ON_EXPIRY_REJECT})
    sr = _classify(_CLAUDE_WS, _conflict_pool(), fs, gate_read=gate)
    assert sr.classification == CONFLICT
    assert sr.needs_gate is False
    assert sr.resolution == EDITED


# -- the durable deadline is frozen in the gate and read against now ------

def test_a_lapsed_gate_auto_approves_when_the_frozen_policy_says_approve():
    # The deadline and on_expiry are frozen in the gate at raise time. On resume,
    # now has passed the frozen deadline, so a pending gate lapses to the frozen
    # on_expiry decision -- approve here -- and overrides to a write.
    path, fs = _rendered(_CLAUDE_WS, [_WBLK])
    _drift(fs, path)
    gate = _gate_reply({"resolution": PENDING, "deadline": 100.0,
                        "on_expiry": ON_EXPIRY_APPROVE})
    sr = _classify(_CLAUDE_WS, _conflict_pool(), fs, gate_read=gate, now=150.0)
    assert sr.classification == OVERRIDDEN
    assert sr.resolution == APPROVED
    assert sr.needs_gate is False


def test_a_lapsed_gate_holds_when_the_frozen_policy_rejects():
    path, fs = _rendered(_CLAUDE_WS, [_WBLK])
    _drift(fs, path)
    gate = _gate_reply({"resolution": PENDING, "deadline": 100.0,
                        "on_expiry": "reject"})
    sr = _classify(_CLAUDE_WS, _conflict_pool(), fs, gate_read=gate, now=150.0)
    assert sr.classification == CONFLICT
    assert sr.resolution == REJECTED
    assert sr.needs_gate is False


def test_a_gate_before_its_frozen_deadline_stays_pending():
    path, fs = _rendered(_CLAUDE_WS, [_WBLK])
    _drift(fs, path)
    gate = _gate_reply({"resolution": PENDING, "deadline": 100.0,
                        "on_expiry": ON_EXPIRY_APPROVE})
    sr = _classify(_CLAUDE_WS, _conflict_pool(), fs, gate_read=gate, now=50.0)
    assert sr.classification == CONFLICT
    assert sr.resolution == PENDING


def test_a_materialized_gate_reply_missing_a_frozen_field_is_a_wiring_fault():
    # The lapse terms (deadline and on_expiry) are frozen into the gate at raise
    # time, so the resume reads them back off the reply, never off a live policy
    # that may since have changed. A materialized (non-None) reply that lacks a
    # frozen field is therefore not a canon-raised gate but a malformed record,
    # and could otherwise fail open: a gate frozen as reject-on-lapse, missing its
    # on_expiry, would silently borrow a live approve-on-lapse and write a conflict
    # no human saw. So it is a loud wiring fault, mirroring an out-of-vocab
    # resolution, never a silent fall-back to live state.
    path, fs = _rendered(_CLAUDE_WS, [_WBLK])
    _drift(fs, path)
    gate = _gate_reply({"resolution": PENDING, "deadline": 100.0})  # no on_expiry
    try:
        _classify(_CLAUDE_WS, _conflict_pool(), fs, gate_read=gate, now=150.0)
    except ValueError:
        return
    raise AssertionError("a gate reply missing a frozen field must raise")


# -- benign skips and structural refusals never gate ----------------------

def test_an_off_limits_surface_is_a_benign_skip():
    path = resolve_surface_path(_CLAUDE_WS, home=HOME, workspace=WS)
    fs = _FakeFS({path: "just prose, no canon region\n"})
    assess, gate = _counting_assessor(), _gate_none()
    sr = _classify(_CLAUDE_WS, [_WBLK], fs, assess=assess, gate_read=gate)
    assert sr.classification == SKIP_OFF_LIMITS
    assert sr.needs_gate is False
    assert assess.calls == []
    assert gate.calls == []


def test_a_missing_surface_is_a_benign_skip():
    fs = _FakeFS({})  # the file is absent
    sr = _classify(_CLAUDE_WS, [_WBLK], fs)
    assert sr.classification == SKIP_MISSING
    assert sr.needs_gate is False


def test_a_refused_surface_never_gates():
    # A region whose declared scope does not match the surface is a structural
    # fault: REFUSED, reported, never a fast-forward and never a human gate.
    path = resolve_surface_path(_CLAUDE_WS, home=HOME, workspace=WS)
    fs = _FakeFS({path: _host("global")})  # workspace surface, global region
    assess, gate = _counting_assessor(), _gate_none()
    sr = _classify(_CLAUDE_WS, [_WBLK], fs, assess=assess, gate_read=gate)
    assert sr.classification == REFUSED
    assert sr.needs_gate is False
    assert gate.calls == []


# -- a malformed gate reply is a loud wiring fault, not a silent hold -----

def test_a_gate_reply_with_an_out_of_vocab_resolution_raises():
    # State is total, but wiring is loud: a gate that returns a resolution canon
    # has no rule for is a wiring fault the caller must see, not a silent hold.
    # The frozen fields are present, so the reply clears the missing-field guard
    # and the out-of-vocab resolution is what raises.
    path, fs = _rendered(_CLAUDE_WS, [_WBLK])
    _drift(fs, path)
    gate = _gate_reply({"resolution": "banana", "deadline": None,
                        "on_expiry": ON_EXPIRY_REJECT})
    try:
        _classify(_CLAUDE_WS, _conflict_pool(), fs, gate_read=gate)
    except ValueError:
        return
    raise AssertionError("an out-of-vocab gate resolution must raise")
