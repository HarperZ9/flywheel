"""Public instruction hygiene: a published repo's instructions stand alone.

Wave 2 established that public repos are NOT canon pointers (they ship and are
cloned standalone, so a pointer to a local canon would be a leak and false on
clone). The invariant instead is: no public instruction file names a local path
or an internal project.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "pub_gate", ROOT / "scripts" / "check_public_instructions.py")
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)


def ws(tmp_path, text):
    (tmp_path / "public" / "demo").mkdir(parents=True)
    (tmp_path / "public" / "demo" / "AGENTS.md").write_text(text, encoding="utf-8")
    return tmp_path


# GENERIC leaks the public gate always catches, with NO operator denylist loaded
# (what CI and a fresh clone see). Private project NAMES are not here: the public
# gate must not itself name them; that detection lives in a gitignored denylist,
# tested separately below.
LEAKY = [
    r'$env:PYTHONPATH = "C:\dev\public\x\src"',
    "See C:/dev/local-model for the harness.",
    "The workspace root instructions still apply.",
    "This is inherited from the parent canon.",
    "Data lives on E:\\local-model-run.",
]
CLEAN = [
    "This is a standalone public utility.",
    "$env:PYTHONPATH = \"../build-color;.\"   # sibling checkout",
    "Never commit secrets or .env files to this public repository.",
    "Claims must be verifiable from this repo alone.",
]


def test_each_leak_shape_is_caught(tmp_path):
    for i, bad in enumerate(LEAKY):
        d = tmp_path / f"case{i}"
        ws(d, bad + "\n")
        assert G.scan(next((d / "public" / "demo").glob("AGENTS.md")), d), bad


def test_clean_public_text_passes(tmp_path):
    d = ws(tmp_path, "\n".join(CLEAN) + "\n")
    assert G.scan(d / "public" / "demo" / "AGENTS.md", d) == []


def test_reports_the_line_number(tmp_path):
    d = ws(tmp_path, "line one\nline two\nsee C:/dev/foo here\n")
    hits = G.scan(d / "public" / "demo" / "AGENTS.md", d)
    assert hits and ":3 " in hits[0]


def test_case_insensitive_drive_letter(tmp_path):
    """The leak the manual grep missed: uppercase C in C:\\dev."""
    d1 = ws(tmp_path / "lo", r"path is c:\dev\x")
    d2 = ws(tmp_path / "hi", r"path is C:\dev\x")
    assert G.scan(d1 / "public" / "demo" / "AGENTS.md", d1)
    assert G.scan(d2 / "public" / "demo" / "AGENTS.md", d2)


def test_the_real_public_tree_is_clean():
    """The gate must pass against the actual public/ tree, or it is theatre."""
    root = ROOT.parent
    if not (root / "public").is_dir():
        import pytest
        pytest.skip("public/ tree not in this checkout")
    leaks = []
    for f in G.public_files(root):
        leaks.extend(G.scan(f, root))
    assert leaks == [], leaks


def test_gate_finds_the_public_files(tmp_path):
    """A gate that scanned nothing passes for free."""
    ws(tmp_path, "clean\n")
    assert len(G.public_files(tmp_path)) == 1


def test_public_repos_outside_public_dir_are_covered(tmp_path, monkeypatch):
    """Wave 3's finding: a repo is public by VISIBILITY, not by living under
    public/. state/emet and behavior-transform.io are public and were unguarded
    until EXTRA_PUBLIC brought them in."""
    (tmp_path / "state" / "demo").mkdir(parents=True)
    leaky = tmp_path / "state" / "demo" / "AGENTS.md"
    leaky.write_text("run from C:/dev/local-model\n", encoding="utf-8")
    monkeypatch.setattr(G, "EXTRA_PUBLIC", ("state/demo",))
    files = G.public_files(tmp_path)
    assert leaky.resolve() in [f.resolve() for f in files]
    assert G.scan(leaky, tmp_path), "a leak in an extra-public repo must be caught"


def test_the_registered_extra_public_repos_are_real_and_clean():
    """The EXTRA_PUBLIC list must point at repos that exist and are clean, or it
    is either stale or masking a leak."""
    root = ROOT.parent
    import pytest
    seen = 0
    for rel in G.EXTRA_PUBLIC:
        d = root / rel
        if not d.exists():
            continue
        for name in ("AGENTS.md", "CLAUDE.md"):
            p = d / name
            if p.is_file():
                seen += 1
                assert G.scan(p, root) == [], f"{rel}/{name} leaks"
    if seen == 0:
        pytest.skip("no EXTRA_PUBLIC repos in this checkout")


def test_private_names_are_caught_only_when_the_denylist_is_present(tmp_path, monkeypatch):
    """The public gate names no private project. Private-name detection comes
    from a gitignored denylist the operator keeps locally, so the shipped gate
    stays clean while local runs still catch a private name."""
    (tmp_path / "public" / "demo").mkdir(parents=True)
    f = tmp_path / "public" / "demo" / "AGENTS.md"
    f.write_text("No secret-project lineage here.\n", encoding="utf-8")
    # no denylist -> generic patterns only -> the private name is NOT flagged
    monkeypatch.setattr(G, "_DENYLIST", tmp_path / "absent.txt")
    monkeypatch.setattr(G, "_RX", G._load_rules())
    assert G.scan(f, tmp_path) == []
    # with a denylist naming it -> flagged
    dl = tmp_path / "deny.txt"
    dl.write_text("secret-project\n", encoding="utf-8")
    monkeypatch.setattr(G, "_DENYLIST", dl)
    monkeypatch.setattr(G, "_RX", G._load_rules())
    assert G.scan(f, tmp_path), "a denylisted private name must be caught when loaded"


def test_the_shipped_gate_file_names_no_private_project():
    """The gate file itself is public; it must not name a private project."""
    src = (ROOT / "scripts" / "check_public_instructions.py").read_text(encoding="utf-8")
    for name in ("opsec/sofer", "sovereign-router"):
        assert name not in src, f"the public gate file names {name!r}"
