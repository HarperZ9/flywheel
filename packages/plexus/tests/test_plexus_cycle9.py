"""Cycle-9 credo falsifiers: honesty repairs to the wiring surface.

These pin the fixes for the "grounded, not asserted" overclaim and its
neighbours: an edge is a DECLARED claim (plexus probes nothing), a duplicate
organ id is NAMED not silently collapsed, the discover output carries a
re-runnable receipt, validate() FAILS on empty-module evidence and never raises
on malformed input, and plan_to reports an honest null instead of fabricating a
command for a tool that declared no CLI.
"""
from pathlib import Path

from plexus.manifest import Manifest, Port, validate
from plexus.mesh import discover
from plexus.plan import plan_to

_ROOT = Path(__file__).resolve().parents[1]


def _m(organ, emits=(), consumes=(), invoke=None):
    return Manifest(organ=organ,
                    invoke=invoke if invoke is not None else {"cli": organ},
                    emits=[e if isinstance(e, Port) else Port(*e) for e in emits],
                    consumes=[c if isinstance(c, Port) else Port(*c) for c in consumes])


# ---------------------------------------------------------------- DEFECT A
# An edge is self-declared: no probe resolves the cited module or runs the tool.
# The surface must tag it "declared", never emit verification vocabulary.

def test_every_edge_is_tagged_declared():
    a = _m("a", emits=[Port("x/1", module="a.py:x")])
    b = _m("b", consumes=[Port("x/1", module="b.py:in")])
    mesh = discover([a, b])
    assert mesh.edges
    for e in mesh.edges:
        assert e.evidence == "declared"          # plexus probed nothing


def test_readme_does_not_use_verification_vocabulary_for_declared_edges():
    text = (_ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "declared, not probed" in text        # the honest heading
    assert "grounded, not asserted" not in text
    assert "traces back to real code" not in text
    assert "genuinely compose" not in text


# ---------------------------------------------------------------- DEFECT B
# A duplicate organ id must be NAMED, not silently resolved last-writer-wins
# (the roster keeps the winner while edges are minted from both).

def test_duplicate_organ_id_is_surfaced_as_a_collision():
    real = _m("crucible", consumes=[Port("x/1", module="real.py:in")])
    impostor = _m("crucible", emits=[Port("y/1", module="evil.py:out")])
    mesh = discover([real, impostor])
    assert "crucible" in mesh.collisions       # the clash is reported, not hidden


def test_no_collision_field_stays_empty_for_a_clean_set():
    a = _m("a", emits=[Port("x/1", module="a.py:x")])
    b = _m("b", consumes=[Port("x/1", module="b.py:in")])
    assert discover([a, b]).collisions == []


def test_validate_set_flags_duplicate_organ_ids():
    from plexus.manifest import duplicate_organs
    assert duplicate_organs([_m("dup"), _m("dup"), _m("solo")]) == ["dup"]
    assert duplicate_organs([_m("a"), _m("b")]) == []


def test_validate_cli_fails_on_organ_collision(tmp_path, capsys):
    import json as _json

    from plexus.cli import main
    (tmp_path / "a.interop.json").write_text(_json.dumps(
        {"organ": "gather", "emits": [{"capability": "x/1", "module": "a.py:x"}]}))
    (tmp_path / "b.interop.json").write_text(_json.dumps(
        {"organ": "gather", "invoke": {"cli": "evil"}}))
    rc = main(["validate", "--dir", str(tmp_path)])
    out = _json.loads(capsys.readouterr().out)
    assert rc == 1                               # collision cannot launder to ok
    assert out["duplicate_organs"] == ["gather"]


# ---------------------------------------------------------------- DEFECT C
# The primary output must carry a re-runnable receipt: per-manifest source +
# content hash, plus the plexus version (tenet 3, no receipt no accept).

def test_content_hash_is_stable_and_binds_content():
    from plexus.manifest import content_hash
    a = _m("t", emits=[Port("x/1", module="a.py:x")])
    b = _m("t", emits=[Port("x/1", module="a.py:x")])
    c = _m("t", emits=[Port("x/1", module="a.py:CHANGED")])
    assert content_hash(a) == content_hash(b)    # same content, same hash
    assert content_hash(a) != content_hash(c)    # a changed pointer changes it
    assert len(content_hash(a)) == 64            # sha256 hex


def test_load_dir_tags_manifest_source(tmp_path):
    import json as _json

    from plexus.registry import builtin_manifests, load_dir
    (tmp_path / "mytool.interop.json").write_text(_json.dumps(
        {"organ": "mytool", "emits": [{"capability": "x/1", "module": "a.py:b"}]}))
    loaded = load_dir(str(tmp_path))
    assert loaded[0].source.endswith("mytool.interop.json")
    assert all(m.source == "builtin:registry" for m in builtin_manifests())


def test_discover_output_carries_a_receipt():
    from plexus.cli import _mesh_json
    from plexus.registry import builtin_manifests
    j = _mesh_json(discover(builtin_manifests()))
    rec = j["receipt"]
    assert rec["plexus_version"]
    assert "generated_utc" in rec
    entries = {e["organ"]: e for e in rec["manifests"]}
    assert entries["gather"]["source"] == "builtin:registry"
    assert all(len(e["sha256"]) == 64 for e in rec["manifests"])


# ---------------------------------------------------------------- DEFECT D
# validate() must be able to FAIL on empty-module evidence: an emit that claims
# a capability with no module pointer is a receipt-less claim under the
# "every edge cites its module" banner.

def test_validate_flags_emit_port_without_module_evidence():
    m = Manifest(organ="t", emits=[Port("x/1")])     # capability, but no module
    assert any("module" in p for p in validate(m))


def test_validate_stays_clean_for_a_grounded_emit():
    m = Manifest(organ="t", emits=[Port("x/1", module="t.py:x")])
    assert validate(m) == []


# ---------------------------------------------------------------- DEFECT E
# The validator contract ("reports malformed input; never raises") must hold on
# the external path: from_dict must not raise on a manifest missing organ or a
# port missing capability.

def test_from_dict_does_not_raise_on_missing_organ():
    m = Manifest.from_dict({"emits": [{"title": "x"}]})   # no organ key
    assert "organ id missing or not a string" in validate(m)


def test_from_dict_tolerates_port_missing_capability():
    m = Manifest.from_dict({"organ": "t", "emits": [{"title": "x"}]})
    assert any("has no capability" in p for p in validate(m))


def test_validate_cli_reports_malformed_file_without_crashing(tmp_path, capsys):
    import json as _json

    from plexus.cli import main
    (tmp_path / "bad.interop.json").write_text('{"emits":[{"title":"x"}]}')
    rc = main(["validate", "--dir", str(tmp_path)])      # must not raise KeyError
    out = _json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["ok"] is not True if "ok" in out else True
    assert "organ id missing or not a string" in out[""]


# ---------------------------------------------------------------- DEFECT F
# plan_to must not fabricate a runnable command for a tool that declared no CLI:
# the absent invocation is an honest null, not the organ id coerced into a command.

def test_plan_marks_hop_nonrunnable_when_no_cli_declared():
    prod = _m("p", invoke={}, emits=[Port("x/1", module="p.py:x")])   # no invoke.cli
    cons = _m("c", invoke={"cli": "c"}, consumes=[Port("x/1", module="c.py:in")])
    hop = next(h for h in plan_to(discover([prod, cons]), "c")["hops"]
               if h["producer"] == "p")
    assert hop["runnable"] is False
    assert "no cli declared" in hop["invoke"]     # absence named, not fabricated


def test_plan_hop_runnable_when_both_clis_declared():
    from plexus.registry import builtin_manifests
    plan = plan_to(discover(builtin_manifests()), "crucible")
    assert plan["hops"] and all(h["runnable"] for h in plan["hops"])
