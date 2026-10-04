"""Vendored helpers stay byte-identical to their canonical releases.

safe_spawn.py is pinned to release 1.0.1 and superstack.py to the superstack
contract release v0.2.0 (FSL-1.1-MIT, like Flywheel), each by the SHA-256 its own release's SHA256SUMS lists.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The canonical SHA-256 of each copy, from that release's own SHA256SUMS:
# safe_spawn.py 1.0.1, and superstack.py v0.2.0 (HarperZ9/superstack, VENDORING.md).
CANONICAL = {"safe_spawn.py": "557d223ba51807a7a2ab89b9bda5c6291a4b4aa2392680e7916c3fdd61bc0a48",
             "superstack.py": "d5f86b29354a43e676d3d2db7005150b100427137e7708be9841f1e7d5589353"}
# Superseded releases, named so an old copy fails with the reason to update, not as an edit.
SUPERSEDED = {
    "cb2dfa9447380f637d294244c6bdf591db1a4a1abf40312a4671b785b8e1bea6": (
        "safe_spawn 1.0.0: a PATH entry that reaches the working folder, or a drive-relative "
        "name such as C:tool, can still start a program planted there"),
}


def _records():
    rows = []
    for line in (ROOT / "VENDORED.sha256").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            digest, rel = line.split(None, 1)
            rows.append((digest.lower(), rel.strip().lstrip("*")))
    return rows


def test_every_vendored_copy_matches_its_record_and_the_canonical_hash():
    rows = _records()
    assert rows, "VENDORED.sha256 lists no copies"
    for digest, rel in rows:
        data = (ROOT / rel).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        assert actual not in SUPERSEDED, f"{rel} is {SUPERSEDED.get(actual)}; copy 1.0.1"
        assert actual == digest, f"{rel} drifted from its record"
        assert CANONICAL.get(Path(rel).name) == digest, f"{rel} is not a canonical release"


def test_every_file_in_the_vendor_folder_is_recorded():
    recorded = {rel for _digest, rel in _records()}
    present = {p.relative_to(ROOT).as_posix()
               for p in (ROOT / "harness" / "_vendor").glob("*.py") if p.name != "__init__.py"}
    assert present == recorded


def test_the_package_imports_the_vendored_helper():
    from harness._vendor import safe_spawn

    assert safe_spawn.SAFE_SPAWN_VERSION == "1.0.1"


def test_the_vendored_contract_is_superstack_0_1_0():
    from harness._vendor import superstack

    assert (superstack.CONTRACT, superstack.VERSION) == ("superstack/0", "0.2.0")
