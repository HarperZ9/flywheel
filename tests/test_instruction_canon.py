"""The instruction drift gate: one canon, every pointer proves it read it.

The load-bearing test is the last one: change the canon, and the pointer goes
stale until a human bumps it. That forced re-read is the whole mechanism.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "canon_gate", ROOT / "scripts" / "check_instruction_canon.py")
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)

CORE = """<!-- CANON-CORE:BEGIN -->
one canon, one source.
line two.
<!-- CANON-CORE:END -->"""


def workspace(tmp_path, *, mirror=CORE, pointer_stamp=None, pointer_body="# delta\n",
              copies=False):
    """Build a fake workspace: canonical CLAUDE.md, mirror AGENTS.md, one pointer,
    and a manifest. Returns (root, manifest_path)."""
    (tmp_path / "CLAUDE.md").write_text("# canon\n" + CORE + "\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# mirror\n" + mirror + "\n", encoding="utf-8")
    (tmp_path / "repo").mkdir()
    if pointer_stamp == "CURRENT":
        pointer_stamp = G.core_hash((tmp_path / "CLAUDE.md").read_text(
            encoding="utf-8"), where="CLAUDE.md")
    body = pointer_body + (CORE + "\n" if copies else "")
    ptr = (f"<!-- canon: CLAUDE.md sha256:{pointer_stamp} -->\n" if pointer_stamp
           else "") + body
    (tmp_path / "repo" / "AGENTS.md").write_text(ptr, encoding="utf-8")
    man = tmp_path / "manifest.json"
    man.write_text('{"canonical":"CLAUDE.md","mirror":"AGENTS.md",'
                   '"pointers":["repo/AGENTS.md"]}', encoding="utf-8")
    return tmp_path, man


def run_verify(tmp_path, monkeypatch, **kw):
    root, man = workspace(tmp_path, **kw)
    monkeypatch.setattr(G, "MANIFEST", man)
    return G.verify(root)


def canon_sha(tmp_path):
    return G.core_hash((tmp_path / "CLAUDE.md").read_text(encoding="utf-8"),
                       where="CLAUDE.md")


# --- drift detection ---------------------------------------------------------

def test_a_missing_stamp_is_drift(tmp_path, monkeypatch):
    probs = run_verify(tmp_path, monkeypatch, pointer_stamp=None)
    assert any("MISSING STAMP" in p for p in probs)


def test_a_stale_stamp_is_drift(tmp_path, monkeypatch):
    probs = run_verify(tmp_path, monkeypatch, pointer_stamp="0" * 64)
    assert any("STALE" in p for p in probs)


def test_a_current_stamp_is_clean(tmp_path, monkeypatch):
    assert run_verify(tmp_path, monkeypatch, pointer_stamp="CURRENT") == []


def test_a_pointer_that_copies_the_canon_is_drift(tmp_path, monkeypatch):
    probs = run_verify(tmp_path, monkeypatch, pointer_stamp="CURRENT", copies=True)
    assert any("COPIES THE CANON" in p for p in probs)


def test_a_mirror_out_of_sync_is_drift(tmp_path, monkeypatch):
    other = CORE.replace("one canon", "a DIFFERENT canon")
    probs = run_verify(tmp_path, monkeypatch, mirror=other, pointer_stamp="CURRENT")
    assert any("MIRROR OUT OF SYNC" in p for p in probs)


def test_crlf_vs_lf_is_not_false_drift(tmp_path, monkeypatch):
    """Canon at c:/dev and pointers in a git repo can differ only in line
    endings; that must not read as drift."""
    root, man = workspace(tmp_path, pointer_stamp="CURRENT")
    a = (tmp_path / "AGENTS.md")
    lf = a.read_text(encoding="utf-8")
    a.write_bytes(lf.replace("\n", "\r\n").encode("utf-8"))   # real CRLF bytes
    monkeypatch.setattr(G, "MANIFEST", man)
    assert not any("MIRROR" in p for p in G.verify(root))


# --- bump resolves drift -----------------------------------------------------

def test_bump_stamps_and_syncs_then_verifies_clean(tmp_path, monkeypatch):
    other = CORE.replace("one canon", "stale mirror")
    root, man = workspace(tmp_path, mirror=other, pointer_stamp="0" * 64)
    monkeypatch.setattr(G, "MANIFEST", man)
    assert G.verify(root), "should start dirty"
    G.bump(root)
    assert G.verify(root) == [], "bump must resolve all drift"


# --- the mechanism: changing the canon forces a re-read ----------------------

def test_changing_the_canon_makes_the_pointer_stale(tmp_path, monkeypatch):
    root, man = workspace(tmp_path, pointer_stamp="x")
    monkeypatch.setattr(G, "MANIFEST", man)
    G.bump(root)
    assert G.verify(root) == []                      # in sync
    canon = tmp_path / "CLAUDE.md"
    canon.write_text(canon.read_text(encoding="utf-8").replace(
        "one canon, one source.", "one canon, AMENDED."), encoding="utf-8")
    probs = G.verify(root)
    assert any("STALE" in p for p in probs), \
        "editing the canon must make every pointer stale until re-read"


# --- the real workspace files verify clean -----------------------------------

def test_the_real_canon_and_pointer_are_in_sync():
    """The gate must pass against the actual workspace, or it is theatre."""
    root = ROOT.parent
    if not (root / "CLAUDE.md").exists():
        pytest.skip("workspace canon not present in this checkout")
    assert G.verify(root) == []


def test_the_real_canon_and_mirror_cores_match():
    root = ROOT.parent
    if not (root / "CLAUDE.md").exists():
        pytest.skip("workspace canon not present")
    c = G.core_hash((root / "CLAUDE.md").read_text(encoding="utf-8"), where="c")
    a = G.core_hash((root / "AGENTS.md").read_text(encoding="utf-8"), where="a")
    assert c == a
