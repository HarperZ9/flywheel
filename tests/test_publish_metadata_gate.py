"""publish_metadata_gate: the frozen baseline, private patterns, and the
publish_public wiring.

Leak strings are built at run time so this file does not itself carry them.
"""
import importlib.util
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _load("publish_metadata_gate")
P = _load("publish_public")
DEV_PATH = "c:" + "/" + "dev" + "/" + "public/x"
SECRET = "orchid" + "-lantern-" + "4471"


def _tree(tmp_path):
    root = tmp_path / "tree"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "fixture.py").write_text(f'P = "{DEV_PATH}"\n', encoding="utf-8")
    (root / "README.md").write_text("clean text\n", encoding="utf-8")
    return root


def _run_gate(root, baseline, deny=None):
    out = io.StringIO()
    code = G.gate(root, baseline, deny_list=deny, all_files=True, stream=out)
    return code, out.getvalue()


def test_frozen_finding_passes_and_growth_blocks(tmp_path):
    root, base = _tree(tmp_path), tmp_path / "base.json"
    assert G.write_baseline(root, base, False, stream=io.StringIO()) == 0
    assert json.loads(base.read_text())["files"] == {"tests/fixture.py": {"local-path": 1}}
    assert _run_gate(root, base)[0] == 0
    with (root / "tests" / "fixture.py").open("a", encoding="utf-8") as f:
        f.write(f'Q = "{DEV_PATH}"\n')
    code, text = _run_gate(root, base)
    assert code == 1
    assert "tests/fixture.py: local-path: 2 finding(s), baseline allows 1" in text


def test_new_file_with_finding_blocks(tmp_path):
    root, base = _tree(tmp_path), tmp_path / "base.json"
    G.write_baseline(root, base, False, stream=io.StringIO())
    (root / "docs.md").write_text(f"see {DEV_PATH}\n", encoding="utf-8")
    code, text = _run_gate(root, base)
    assert code == 1 and "docs.md: local-path" in text


def test_deny_list_hit_always_blocks_and_value_is_never_printed(tmp_path):
    root, base = _tree(tmp_path), tmp_path / "base.json"
    (root / "README.md").write_text(f"token {SECRET}\n", encoding="utf-8")
    G.write_baseline(root, base, False, stream=io.StringIO())
    deny = tmp_path / "deny.txt"
    deny.write_text(SECRET + "\n", encoding="utf-8")
    assert "deny-list" not in base.read_text()
    code, text = _run_gate(root, base, str(deny))
    assert code == 1 and "README.md: deny-list" in text
    assert SECRET not in text
    assert _run_gate(root, base)[0] == 0


def test_baseline_only_shrinks(tmp_path):
    root, base = _tree(tmp_path), tmp_path / "base.json"
    G.write_baseline(root, base, False, stream=io.StringIO())
    (root / "more.md").write_text(f"{DEV_PATH}\n", encoding="utf-8")
    out = io.StringIO()
    assert G.write_baseline(root, base, False, stream=out) == 1
    assert "refused" in out.getvalue()
    assert G.write_baseline(root, base, True, stream=io.StringIO()) == 0
    (root / "more.md").unlink()
    (root / "tests" / "fixture.py").write_text("clean\n", encoding="utf-8")
    assert G.write_baseline(root, base, False, stream=io.StringIO()) == 0
    assert json.loads(base.read_text())["files"] == {}


def test_committed_baseline_is_counts_only():
    data = json.loads(G.BASELINE.read_text(encoding="utf-8"))
    assert data["schema"] == G.SCHEMA
    for rel, cats in data["files"].items():
        assert not Path(rel).is_absolute() and ":" not in rel
        assert all(isinstance(n, int) and n > 0 for n in cats.values())
        assert "deny-list" not in cats and "machine-name" not in cats


def test_publish_export_never_copies_the_deny_list(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "tool.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "scripts" / ".publish-denylist.txt").write_text(SECRET + "\n", encoding="utf-8")
    monkeypatch.setattr(P, "REPO", repo)
    copied = P.export_subset(tmp_path / "staging")
    assert (tmp_path / "staging" / "scripts" / "tool.py").is_file()
    assert not (tmp_path / "staging" / "scripts" / ".publish-denylist.txt").exists()
    assert all(".publish-denylist" not in c for c in copied)


def test_publish_aborts_before_push_when_metadata_gate_fails(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(P, "export_subset", lambda staging: [])
    monkeypatch.setattr(P, "lint_gate", lambda staging: 0)
    monkeypatch.setattr(P, "metadata_gate", lambda staging, deny: calls.append(deny) or 1)
    monkeypatch.setattr(P, "publish", lambda *a: calls.append("pushed") or 0)
    monkeypatch.setattr(P, "check_public_remote", lambda: True)
    code = P.main(["--staging", str(tmp_path / "s"), "--deny-list", "d.txt"])
    assert code == 1 and calls == ["d.txt"]


def test_publish_metadata_gate_runs_on_a_real_staging_tree(tmp_path):
    root = _tree(tmp_path)
    (root / "README.md").write_text(f"{DEV_PATH}\n", encoding="utf-8")
    assert P.metadata_gate(root) == 1
