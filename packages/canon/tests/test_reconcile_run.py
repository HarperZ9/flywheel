"""test_reconcile_run.py -- V4: the two-phase reconcile orchestrator.

reconcile walks canon's managed surfaces and, per surface, classifies the state
(classify_surface) then acts on it. It is two-phase by construction: every
surface is classified first, reading only; then the commit phase writes the
fast-forwards and overrides, raises a fresh gate for each unresolved conflict or
held surface, and witnesses the whole run once. A conflict raised this run
freezes its durable deadline (now + policy window) and on_expiry into the gate,
the exact record classify_surface reads back on a later resume.

All IO (read_text/write_text), the crucible assessor, the gate reader and
raiser, the clock, and the run witness are injected, so no real file, engine, or
gate store is touched.
"""
from __future__ import annotations

import os

from canon.persona_thesis import DriftVerdict
from canon.reconcile import (
    CONFLICT,
    FAST_FORWARD,
    FOLD_NONE,
    IN_SYNC,
    OVERRIDDEN,
    REFUSED,
    SKIP_MISSING,
    SKIP_OFF_LIMITS,
)
from canon.reconcile_gate import (
    APPROVED,
    ON_EXPIRY_APPROVE,
    ON_EXPIRY_REJECT,
    ConflictGatePolicy,
)
from canon.reconcile_run import ReconcileReport, reconcile, reconcile_exit_code
from canon.registry import (
    SURFACE_CATALOG,
    resolve_surface_path,
    write_surfaces,
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


# -- local fakes and builders (per-file convention, as test_drift/reconcile) --

class _FakeFS:
    def __init__(self, files=None):
        self.files = dict(files or {})
        self.writes = []

    def read_text(self, path):
        return self.files.get(path)

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
    prov = Provenance(harness="claude-code", source_hash="a" * 64, create_ord=ord)
    return Record(kind=KIND_PERSONALITY_BLOCK, id=id, scope=scope,
                  data={"title": id.title(), "body": body}, provenance=prov)


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


def _surface(harness: str, scope: str):
    for s in SURFACE_CATALOG:
        if s.harness == harness and s.scope == scope:
            return s
    raise KeyError((harness, scope))


def _gate_none():
    def gate_read(key):
        return None
    return gate_read


def _gate_reply(reply):
    def gate_read(key):
        return reply
    return gate_read


def _recorder():
    calls = []

    def fn(payload):
        calls.append(payload)

    fn.calls = calls
    return fn


_WBLK = _rblock("tone", "workspace", "W tone")
_GBLK = _rblock("mission", "global", "G mission")


def _seed(fs, surface, blocks):
    """Seed `surface`'s host with the clean batch render, matching what both
    surface_drift and the reconcile commit re-derive."""
    path = resolve_surface_path(surface, home=HOME, workspace=WS)
    fs.files[path] = _host(surface.scope)
    write_surfaces(blocks, home=HOME, workspace=WS, read_text=fs.read_text,
                   write_text=fs.write_text, surfaces=(surface,))
    fs.writes.clear()
    return path


def _drift(fs, path):
    fs.files[path] = fs.files[path].replace(
        "<!-- canon:end -->", "drifted line\n<!-- canon:end -->")


def _drifted_workspace_pool():
    """A workspace persona whose basis is superseded: a proven DRIFT."""
    wp = _persona("wp", "workspace", source_ids=["s1"])
    return [_WBLK, wp, _source("s1", scope="workspace"),
            _source("s1-new", scope="workspace", supersedes="s1", ord=300)]


def _run(fs, pool, *, surfaces, assess=None, gate_read=None, gate_raise=None,
         witness=None, policy=ConflictGatePolicy(), now=0, run_ord=7):
    return reconcile(
        pool, home=HOME, workspace=WS, read_text=fs.read_text,
        write_text=fs.write_text,
        assess=assess if assess is not None else _ladder_assessor(),
        gate_read=gate_read if gate_read is not None else _gate_none(),
        gate_raise=gate_raise if gate_raise is not None else _recorder(),
        run_ord=run_ord, policy=policy, now=now, witness=witness,
        surfaces=surfaces)


# -- an all-clean run writes nothing, raises nothing, is ok ---------------

def test_an_all_clean_run_writes_nothing_and_is_ok():
    fs = _FakeFS()
    s = _surface("codex", "workspace")
    _seed(fs, s, [_WBLK])
    wit = _recorder()
    report = _run(fs, [_WBLK], surfaces=(s,), witness=wit)
    assert isinstance(report, ReconcileReport)
    assert report.ok is True
    assert report.committed == ()
    assert report.gates_raised == ()
    assert fs.writes == []
    assert report.surfaces[0].classification == IN_SYNC
    assert report.witnessed is True
    assert len(wit.calls) == 1  # the witness fires once, even all-clean


# -- a fast-forward commits its write -------------------------------------

def test_a_fast_forward_commits_the_write():
    fs = _FakeFS()
    s = _surface("codex", "workspace")
    path = _seed(fs, s, [_WBLK])
    _drift(fs, path)
    report = _run(fs, [_WBLK], surfaces=(s,))
    assert path in fs.writes
    assert report.committed == (path,)
    assert report.surfaces[0].classification == FAST_FORWARD
    assert report.ok is True


# -- a conflict raises a gate and writes nothing --------------------------

def test_a_conflict_raises_a_gate_and_writes_nothing():
    fs = _FakeFS()
    s = _surface("hermes", "workspace")
    path = _seed(fs, s, [_WBLK])
    _drift(fs, path)
    raise_fn = _recorder()
    report = _run(fs, _drifted_workspace_pool(), surfaces=(s,),
                  gate_raise=raise_fn)
    assert fs.writes == []
    assert report.committed == ()
    assert len(report.gates_raised) == 1
    assert report.gates_raised[0]["harness"] == "hermes"
    assert report.gates_raised[0]["path"] == "SOUL.md"
    assert report.surfaces[0].classification == CONFLICT
    assert report.ok is False
    assert len(raise_fn.calls) == 1


# -- an approved gate commits an override and never re-raises -------------

def test_an_approved_gate_commits_an_override():
    fs = _FakeFS()
    s = _surface("hermes", "workspace")
    path = _seed(fs, s, [_WBLK])
    _drift(fs, path)
    raise_fn = _recorder()
    report = _run(fs, _drifted_workspace_pool(), surfaces=(s,),
                  gate_read=_gate_reply({"resolution": APPROVED,
                                         "deadline": None,
                                         "on_expiry": ON_EXPIRY_REJECT}),
                  gate_raise=raise_fn)
    assert path in fs.writes
    assert report.committed == (path,)
    assert report.gates_raised == ()
    assert report.surfaces[0].classification == OVERRIDDEN
    assert report.ok is True
    assert raise_fn.calls == []


# -- the raised gate freezes the absolute deadline and on_expiry ----------

def test_a_bounded_policy_freezes_the_absolute_deadline():
    fs = _FakeFS()
    s = _surface("hermes", "workspace")
    path = _seed(fs, s, [_WBLK])
    _drift(fs, path)
    policy = ConflictGatePolicy(deadline_seconds=3600.0,
                                on_expiry=ON_EXPIRY_APPROVE)
    report = _run(fs, _drifted_workspace_pool(), surfaces=(s,), policy=policy,
                  now=1000.0)
    g = report.gates_raised[0]
    assert g["deadline"] == 4600.0  # now + window, frozen at raise
    assert g["on_expiry"] == ON_EXPIRY_APPROVE


def test_an_unbounded_policy_freezes_a_none_deadline():
    fs = _FakeFS()
    s = _surface("hermes", "workspace")
    path = _seed(fs, s, [_WBLK])
    _drift(fs, path)
    report = _run(fs, _drifted_workspace_pool(), surfaces=(s,), now=1000.0)
    assert report.gates_raised[0]["deadline"] is None


# -- two-phase: classify every surface before acting on any ---------------

def test_a_run_classifies_all_surfaces_before_it_acts():
    # A fast-forward and a conflict share one run and one pool, split by scope: a
    # sound workspace persona fast-forwards the workspace file, a drifted global
    # persona conflicts the global file. The fast-forward commits, the conflict
    # raises, and the witness fires once over the whole run.
    fs = _FakeFS()
    ws_s = _surface("claude-code", "workspace")
    gl_s = _surface("claude-code", "global")
    ws_path = _seed(fs, ws_s, [_WBLK, _GBLK])
    gl_path = _seed(fs, gl_s, [_WBLK, _GBLK])
    _drift(fs, ws_path)
    _drift(fs, gl_path)
    pool = [
        _WBLK, _GBLK,
        _persona("wp", "workspace", source_ids=["sw"]),
        _source("sw", scope="workspace"),
        _persona("gp", "global", source_ids=["sg"]),
        _source("sg", scope="global"),
        _source("sg-new", scope="global", supersedes="sg", ord=300),
    ]
    wit, raise_fn = _recorder(), _recorder()
    report = _run(fs, pool, surfaces=(ws_s, gl_s), gate_raise=raise_fn,
                  witness=wit)
    assert ws_path in fs.writes           # the fast-forward committed
    assert report.committed == (ws_path,)
    assert len(report.gates_raised) == 1  # the conflict raised
    assert report.gates_raised[0]["scope"] == "global"
    assert len(wit.calls) == 1            # the witness fired once
    assert report.ok is False             # a conflict remains unresolved


# -- witness is optional --------------------------------------------------

def test_no_witness_means_not_witnessed():
    fs = _FakeFS()
    s = _surface("codex", "workspace")
    _seed(fs, s, [_WBLK])
    report = _run(fs, [_WBLK], surfaces=(s,), witness=None)
    assert report.witnessed is False


# -- benign skips are ok, structural refusals are not ---------------------

def test_off_limits_and_missing_are_ok_skips():
    fs = _FakeFS()
    off = _surface("codex", "workspace")
    fs.files[resolve_surface_path(off, home=HOME, workspace=WS)] = "prose\n"
    # hermes SOUL.md left absent entirely -> missing
    miss = _surface("hermes", "workspace")
    report = _run(fs, [_WBLK], surfaces=(off, miss))
    kinds = {sr.surface.harness: sr.classification for sr in report.surfaces}
    assert kinds["codex"] == SKIP_OFF_LIMITS
    assert kinds["hermes"] == SKIP_MISSING
    assert report.ok is True
    assert report.committed == ()
    assert report.gates_raised == ()
    assert fs.writes == []


def test_a_refused_surface_is_not_ok_and_never_gates():
    fs = _FakeFS()
    s = _surface("hermes", "workspace")
    # a workspace surface whose on-disk region declares the global scope
    fs.files[resolve_surface_path(s, home=HOME, workspace=WS)] = _host("global")
    raise_fn = _recorder()
    report = _run(fs, _drifted_workspace_pool(), surfaces=(s,),
                  gate_raise=raise_fn)
    assert report.surfaces[0].classification == REFUSED
    assert report.ok is False
    assert report.gates_raised == ()
    assert raise_fn.calls == []
    assert fs.writes == []


# -- the run witness: a path-clean, pool-bound receipt of the run ----------

def test_the_witness_payload_names_the_run_and_binds_the_pool():
    fs = _FakeFS()
    s = _surface("codex", "workspace")
    _seed(fs, s, [_WBLK])
    wit = _recorder()
    _run(fs, [_WBLK], surfaces=(s,), witness=wit, run_ord=42)
    (payload,) = wit.calls
    assert payload["kind"] == "canon_reconcile_run"
    assert payload["run_ord"] == 42
    assert len(payload["pool_digest"]) == 64  # a sha256 over the pool
    assert payload["ok"] is True
    assert len(payload["surfaces"]) == 1


def test_witness_rows_are_path_clean_never_absolute():
    fs = _FakeFS()
    s = _surface("codex", "workspace")
    _seed(fs, s, [_WBLK])
    wit = _recorder()
    _run(fs, [_WBLK], surfaces=(s,), witness=wit)
    row = wit.calls[0]["surfaces"][0]
    assert row["path"] == "AGENTS.md"      # the surface's relative path
    assert "fake" not in row["path"]       # never the absolute host path
    assert row["harness"] == "codex"
    assert row["scope"] == "workspace"
    assert row["classification"] == IN_SYNC
    assert row["drift"] == "match"
    assert row["persona_fold"] == FOLD_NONE
    assert row["committed"] is False


def test_a_fast_forward_row_binds_both_region_hashes():
    fs = _FakeFS()
    s = _surface("codex", "workspace")
    path = _seed(fs, s, [_WBLK])
    _drift(fs, path)
    wit = _recorder()
    _run(fs, [_WBLK], surfaces=(s,), witness=wit)
    row = wit.calls[0]["surfaces"][0]
    assert row["classification"] == FAST_FORWARD
    assert row["committed"] is True
    assert len(row["expected_sha256"]) == 64
    assert len(row["actual_sha256"]) == 64
    assert row["expected_sha256"] != row["actual_sha256"]  # the drift moved bytes


def test_an_off_limits_row_carries_null_hashes():
    fs = _FakeFS()
    s = _surface("codex", "workspace")
    fs.files[resolve_surface_path(s, home=HOME, workspace=WS)] = "prose\n"
    wit = _recorder()
    _run(fs, [_WBLK], surfaces=(s,), witness=wit)
    row = wit.calls[0]["surfaces"][0]
    assert row["classification"] == SKIP_OFF_LIMITS
    assert row["expected_sha256"] is None
    assert row["actual_sha256"] is None
    assert row["committed"] is False


def test_the_pool_digest_is_deterministic_and_pool_sensitive():
    fs = _FakeFS()
    s = _surface("codex", "workspace")
    _seed(fs, s, [_WBLK])
    a, b = _recorder(), _recorder()
    _run(fs, [_WBLK], surfaces=(s,), witness=a)
    _run(fs, [_WBLK], surfaces=(s,), witness=b)
    assert a.calls[0]["pool_digest"] == b.calls[0]["pool_digest"]
    c = _recorder()
    _run(fs, [_WBLK, _GBLK], surfaces=(s,), witness=c)
    assert c.calls[0]["pool_digest"] != a.calls[0]["pool_digest"]


def test_reconcile_exit_code_gates_a_build():
    fs = _FakeFS()
    s = _surface("codex", "workspace")
    _seed(fs, s, [_WBLK])
    clean = _run(fs, [_WBLK], surfaces=(s,))
    assert reconcile_exit_code(clean) == 0

    fs2 = _FakeFS()
    r = _surface("hermes", "workspace")
    fs2.files[resolve_surface_path(r, home=HOME, workspace=WS)] = _host("global")
    dirty = _run(fs2, _drifted_workspace_pool(), surfaces=(r,))
    assert reconcile_exit_code(dirty) == 1
