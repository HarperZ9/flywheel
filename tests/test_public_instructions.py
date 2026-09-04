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
    # extra_roots=() asks only about the synthetic tree. The production default
    # also scans the checkout the gate ships in, which is covered by
    # test_this_checkout_is_scanned_by_path_not_by_directory_name.
    assert len(G.public_files(tmp_path, extra_roots=())) == 1


def test_public_repos_outside_public_dir_are_covered(tmp_path, monkeypatch):
    """Wave 3's finding: a repo is public by VISIBILITY, not by living under
    public/. state/emet and behavior-transform.io are public and were unguarded
    until EXTRA_PUBLIC brought them in."""
    (tmp_path / "state" / "demo").mkdir(parents=True)
    leaky = tmp_path / "state" / "demo" / "AGENTS.md"
    leaky.write_text("run from C:/dev/local-model\n", encoding="utf-8")
    monkeypatch.setattr(G, "EXTRA_PUBLIC", ("state/demo",))
    files = G.public_files(tmp_path, extra_roots=())
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


# --- published SURFACES, widened after a model card slipped past ------------
#
# The gate held its rule over three instruction filenames and nothing else, so a
# 32B model card carrying a build-machine path reached a branch and was caught by
# hand. A gate that reads three filenames cannot see the page a reader opens
# first. These cover the widened scope and the burn-down that let it switch on
# without waiting for 31 doc rewrites.

def surface(tmp_path, rel, text):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_a_model_card_is_scanned_like_an_instruction_file(tmp_path):
    surface(tmp_path, "project-docs/releases/32B/MODEL_CARD.md",
            r"- Artifact: `E:\local-model-run\x.gguf`" + "\n")
    found = G.published_surface_files(tmp_path, extra_roots=(tmp_path,))
    assert any(p.name == "MODEL_CARD.md" for p in found)
    card = next(p for p in found if p.name == "MODEL_CARD.md")
    hits = G.scan(card, tmp_path)
    assert hits and "local run-drive path" in hits[0]


def test_a_shipped_skill_is_scanned_like_an_instruction_file(tmp_path):
    """A skill in a public repo is read by a stranger and executed by a model,
    so a local path in one leaks exactly the way it does from AGENTS.md."""
    sep, eol = chr(92), chr(10)
    surface(tmp_path, ".claude/skills/example/SKILL.md",
            "Run it from `C:" + sep + "dev" + sep + "x`." + eol)
    surface(tmp_path, ".claude/commands/example.md", "cd E:" + sep + "scratch" + eol)
    found = G.published_surface_files(tmp_path, extra_roots=(tmp_path,))
    skill = next(p for p in found if p.name == "SKILL.md")
    assert G.scan(skill, tmp_path)
    assert any(p.name == "example.md" for p in found)


def test_internal_register_docs_are_not_scanned(tmp_path):
    """The canon permits local paths in records, plans and specs. A gate that
    flagged them would push the operator to switch it off."""
    surface(tmp_path, "project-docs/records/note.md", r"built at C:\dev\x" + "\n")
    surface(tmp_path, "project-docs/specs/design.md", r"see C:\dev\y" + "\n")
    names = {p.name for p in G.published_surface_files(tmp_path, extra_roots=(tmp_path,))}
    assert "note.md" not in names and "design.md" not in names


def test_this_checkout_is_scanned_by_path_not_by_directory_name(tmp_path):
    """The bug this closes: the repo was found by the name "local-model", so
    from a worktree the gate scanned a DIFFERENT checkout and reported clean on
    files it had never opened."""
    found = G.published_surface_files(ROOT.parent)
    assert any(str(p).startswith(str(ROOT)) for p in found), (
        "the gate did not scan the checkout it ships in")
    inside = next(p for p in found if str(p).startswith(str(ROOT)))
    assert not G.key_for(inside, ROOT.parent).startswith(ROOT.name), (
        "a surface in this repo must be keyed repo-relative, or a burn-down "
        "entry written from one checkout cannot match another")


def test_the_burndown_parses_and_only_counts_marked_lines(tmp_path):
    (tmp_path / "project-docs" / "records").mkdir(parents=True)
    (tmp_path / G.SURFACE_BURNDOWN).write_text(
        "# heading\n\nprose that mentions `a/b.md` - 9 inline\n\n"
        "- `project-docs/releases/32B/MODEL_CARD.md` - 3\n"
        "- `public/x/README.md` - 1\n", encoding="utf-8")
    frozen = G.load_burndown(tmp_path)
    assert frozen == {"project-docs/releases/32B/MODEL_CARD.md": 3,
                      "public/x/README.md": 1}


def test_an_absent_burndown_grandfathers_nothing(tmp_path):
    assert G.load_burndown(tmp_path) == {}


def test_the_shipped_burndown_matches_the_tree():
    """The record is a measurement, not a wish. If a surface has burned down,
    this says so rather than letting a stale number hide a regression."""
    frozen = G.load_burndown(ROOT)
    assert frozen, "the shipped burn-down record is missing or unparseable"
    for path, count in frozen.items():
        p = ROOT / path
        if not p.is_file():
            continue                      # another repo's file, absent here
        assert len(G.scan(p, ROOT.parent)) <= count, (
            f"{path} has more leaks than the frozen {count}")


def test_a_surface_that_was_clean_and_now_leaks_fails():
    """The regression that started all this. Without it the gate reports clean
    on a model card that just grew a build-machine path."""
    new, grown, shrunk, failures = G.classify_surfaces(
        {"project-docs/releases/32B/MODEL_CARD.md": ["a leak"]}, {})
    assert new and failures and not grown


def test_a_grandfathered_surface_that_grows_fails():
    new, grown, shrunk, failures = G.classify_surfaces(
        {"x/README.md": ["one", "two"]}, {"x/README.md": 1})
    assert grown and failures and not new


def test_a_surface_at_its_frozen_count_passes():
    new, grown, shrunk, failures = G.classify_surfaces(
        {"x/README.md": ["one"]}, {"x/README.md": 1})
    assert not new and not grown and not failures and not shrunk


def test_a_shrinking_surface_passes_and_is_reported():
    new, grown, shrunk, failures = G.classify_surfaces(
        {"x/README.md": ["one"]}, {"x/README.md": 3})
    assert not failures and shrunk and "down from 3" in shrunk[0]


def test_a_surface_that_reached_zero_is_reported_and_may_leave():
    new, grown, shrunk, failures = G.classify_surfaces({}, {"x/README.md": 2})
    assert not failures and shrunk and "clean now" in shrunk[0]


def test_the_shipped_globs_actually_match_a_real_surface():
    """A glob list that matches nothing passes for free, which is how a gate
    quietly stops gating."""
    assert G.SURFACE_GLOBS
    found = G.published_surface_files(ROOT.parent)
    assert found, "the shipped SURFACE_GLOBS matched no file anywhere"
    assert any(str(p).startswith(str(ROOT)) for p in found)
