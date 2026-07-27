"""The declared Python floor must be true, and the verifier must stay portable.

Both halves of this were wrong at once and nothing noticed. `pyproject.toml` said
`>=3.10` while 51 modules imported `datetime.UTC`, which is 3.11+, so the package
could not import on its own declared floor. CI dutifully tested 3.10 and went red
for a reason that said nothing about the code, which is how a permanently failing
leg stops being read.

So two invariants, checked rather than asserted in prose:

  1. The declared floor is at least as high as the newest language or stdlib
     feature actually used.
  2. The VERIFIER closure does not acquire such a feature. A stranger checking a
     receipt should not be forced onto a newer interpreter than the check needs,
     and that is a claim this repo makes in `pyproject.toml`.
"""
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Stdlib names that raise the floor, with the version that introduced them.
# Keyed by a regex over source text. Add to this when a new one is adopted.
VERSION_GATED = [
    (re.compile(r"from datetime import[^\n]*\bUTC\b|\bdatetime\.UTC\b"),
     (3, 11), "datetime.UTC"),
    (re.compile(r"\bimport tomllib\b|\bfrom tomllib\b"),
     (3, 11), "tomllib"),
    (re.compile(r"\bfrom typing import[^\n]*\boverride\b"),
     (3, 12), "typing.override"),
    (re.compile(r"\bitertools\.batched\b"),
     (3, 12), "itertools.batched"),
]


def declared_floor() -> tuple[int, int]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^requires-python\s*=\s*"[><=~^]*(\d+)\.(\d+)"', text,
                  re.MULTILINE)
    assert m, "pyproject.toml declares no requires-python"
    return int(m.group(1)), int(m.group(2))


def _sources(*dirs):
    for d in dirs:
        for p in sorted((ROOT / d).rglob("*.py")):
            if "__pycache__" not in p.parts:
                yield p


def features_used(paths) -> dict:
    """{(major, minor): [ "feature -> file", ... ]} for everything found."""
    found: dict = {}
    for p in paths:
        text = p.read_text(encoding="utf-8", errors="replace")
        for rx, ver, name in VERSION_GATED:
            if rx.search(text):
                rel = p.relative_to(ROOT).as_posix()
                found.setdefault(ver, []).append(f"{name} -> {rel}")
    return found


def test_the_declared_floor_is_not_below_what_the_code_uses():
    floor = declared_floor()
    used = features_used(_sources("harness", "scripts"))
    too_new = {v: w for v, w in used.items() if v > floor}
    assert not too_new, (
        f"pyproject.toml declares >={floor[0]}.{floor[1]} but the code uses "
        f"features from newer versions: "
        + "; ".join(f"{v[0]}.{v[1]} ({len(w)} files, e.g. {w[0]})"
                    for v, w in sorted(too_new.items()))
    )


def test_the_floor_claim_is_not_vacuous():
    """If nothing in the tree were version-gated, the test above would pass for
    free and would not be watching anything. It is currently 3.11 that binds."""
    used = features_used(_sources("harness", "scripts"))
    assert used, "no version-gated feature found; the floor check is watching nothing"
    assert max(used) == declared_floor(), (
        "the declared floor should be exactly the highest feature in use, "
        f"which is {max(used)}; declaring higher locks out users for no reason")


def test_the_ci_matrix_does_not_test_below_the_floor():
    """Testing a version the package cannot import on is a red leg that carries
    no information."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    m = re.search(r"python:\s*\[([^\]]+)\]", ci)
    assert m, "no python matrix found in ci.yml"
    versions = [tuple(int(x) for x in v.strip().strip('"\'').split("."))
                for v in m.group(1).split(",")]
    floor = declared_floor()
    below = [v for v in versions if v < floor]
    assert not below, (
        f"ci tests {below} but the declared floor is {floor}")
    assert floor in versions, (
        f"ci does not test the declared floor {floor}; the oldest supported "
        "interpreter is exactly the one most likely to break")


def test_the_verifier_closure_stays_on_the_lowest_interpreter_it_needs():
    """The claim in pyproject.toml: a stranger checking a receipt is not bound by
    the package floor. That only stays true if the closure stays clean."""
    spec = importlib.util.spec_from_file_location(
        "vs", ROOT / "scripts" / "check_verifier_stdlib.py")
    vs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vs)
    reached, _ = vs.closure(vs.VERIFIER_ENTRY_POINTS)
    # The closure yields relative-import names like "..merkle" or
    # "..certificates.crossing". Every one must resolve to a file: a name that
    # quietly failed to resolve would shrink what this test examines while it
    # still reported success.
    paths, unresolved = [], []
    for mod in sorted(reached):
        rel = mod.lstrip(".").replace(".", "/")
        for cand in (ROOT / "harness" / f"{rel}.py", ROOT / f"{rel}.py"):
            if cand.is_file():
                paths.append(cand)
                break
        else:
            unresolved.append(mod)
    assert not unresolved, f"closure names did not resolve to files: {unresolved}"
    assert len(paths) == len(reached)
    used = features_used(paths)
    assert used == {}, (
        "the verifier closure now needs a newer interpreter: "
        f"{used}. The accept path is what strangers run; keep it portable.")
