"""The vendored safe_spawn is the canonical 1.0.1 file, byte for byte.

Per-tool choices are call arguments, so an edit to the copy is a defect. The
record is ``VENDORED.sha256`` at the repository root, in ``sha256sum`` format;
the conformance kit checks the same record against the canonical sums.
"""
import hashlib
from pathlib import Path

from relay._vendor import safe_spawn

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = {"557d223ba51807a7a2ab89b9bda5c6291a4b4aa2392680e7916c3fdd61bc0a48": "safe_spawn.py"}
# Released copies a later version replaces, with the reason to update.
SUPERSEDED = {
    "cb2dfa9447380f637d294244c6bdf591db1a4a1abf40312a4671b785b8e1bea6":
        "safe_spawn 1.0.0: a PATH entry that reaches the working folder, or a "
        "drive-relative name such as C:tool, can still start a program planted there",
}


def _record():
    rows = {}
    for line in (ROOT / "VENDORED.sha256").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            digest, rel = line.split(None, 1)
            rows[rel.strip()] = digest
    return rows


def test_every_recorded_copy_matches_its_bytes_and_a_canonical_hash():
    rows = _record()
    for digest in rows.values():
        assert digest not in SUPERSEDED, f"superseded copy recorded: {SUPERSEDED.get(digest)}"
    assert rows == {"src/relay/_vendor/safe_spawn.py": next(iter(CANONICAL))}
    for rel, digest in rows.items():
        actual = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        assert actual == digest, f"{rel} was edited or checked out with CRLF"
        assert CANONICAL[digest] == Path(rel).name


def test_the_imported_module_is_the_recorded_file():
    assert safe_spawn.SAFE_SPAWN_VERSION == "1.0.1"
    assert Path(safe_spawn.__file__).resolve() == ROOT / "src/relay/_vendor/safe_spawn.py"


def test_the_copy_is_pinned_against_line_ending_conversion():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "**/_vendor/safe_spawn.py -text" in " ".join(attrs.split())
