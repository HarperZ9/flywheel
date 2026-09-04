"""documentation_maintenance/v2: a checker an echo of its own fixture cannot pass.

The null floor in `cross_harness_null_adapters` found that v1 scores a
submission that hands the fixture back verbatim. Everything v1 compares
(surface names, paths, code refs) is present in the fixture, so transcription
is indistinguishable from work.

v2 keeps every v1 comparison and adds one thing the fixture cannot supply: the
sha256 of each documentation surface and of each code reference, read from the
workspace. A candidate has to open the files. Echoing the fixture yields no
digests, and hollowing the fields yields empty ones.

v1 is left alone rather than tightened in place. A run scored under v1 stays
comparable to itself, and the version number carries the change.
"""
from __future__ import annotations

import hashlib
from typing import Any

CHECKER_ID = "documentation_maintenance/v2"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rows(value: Any, field: str, malformed) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise malformed(f"{field}_type_invalid")
    return value


def _strings(value: Any, field: str, malformed) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise malformed(f"{field}_type_invalid")
    return value


def documentation_maintenance_v2(context, report, texts, fixture, checked):
    """Same surfaces as v1, plus digests that require reading the workspace."""
    from harness.cross_harness_oracles import _Malformed, _claim_violation, _inside, _read, _root

    rows = _rows(fixture.get("surfaces"), "fixture_surfaces", _Malformed)
    reported = _rows(report.get("surfaces"), "surfaces", _Malformed)
    for row in rows + reported:
        if not isinstance(row.get("surface"), str) or not isinstance(row.get("path"), str):
            raise _Malformed("surface_entry_type_invalid")
        _strings(row.get("code_refs"), "code_refs", _Malformed)

    expected_names = sorted(_strings(context.oracle_spec.get("expected_surfaces"),
                                     "expected_surfaces", _Malformed))
    fixture_names = sorted(str(row.get("surface", "")) for row in rows)
    reported_names = sorted(str(row.get("surface", "")) for row in reported)
    reference = {row.get("surface"): row for row in rows}
    root = _root(context, "workspace_root")
    codes: list[str] = []

    if fixture_names != expected_names or len(fixture_names) != len(set(fixture_names)):
        codes.append("fixture_surface_set_invalid")
    if reported_names != fixture_names:
        codes.append("surface_set_mismatch")

    for row in reported:
        name = row.get("surface")
        expected_row = reference.get(name, {})
        path = _inside(root, row.get("path"))
        if path is None:
            codes.append("surface_path_invalid")
        else:
            codes.extend(_digest_codes(row, "content_sha256",
                                       [_sha(_read(checked, f"workspace:surface:{name}", path))]))
        if not expected_row:
            continue
        refs = _strings(row.get("code_refs"), "code_refs", _Malformed)
        if refs != expected_row.get("code_refs"):
            codes.append("code_refs_mismatch")
        actual: list[str] = []
        for index, ref in enumerate(refs):
            ref_path = _inside(root, ref)
            if ref_path is None:
                codes.append("surface_path_invalid")
                continue
            actual.append(_sha(_read(checked, f"workspace:code_ref:{name}:{index}", ref_path)))
        if len(actual) == len(refs):
            codes.extend(_digest_codes(row, "code_ref_sha256s", actual,
                                       plural=True, mismatch="code_ref_digest_mismatch"))
        if row.get("path") != expected_row.get("path"):
            codes.append("surface_path_invalid")

    if _claim_violation(texts):
        codes.append("claim_language_violation")
    return codes


def _digest_codes(row, field: str, actual: list[str], *, plural: bool = False,
                  mismatch: str = "surface_digest_mismatch") -> list[str]:
    """Compare a reported digest against one read from the workspace.

    A missing field and a wrong field are separate codes. The first says the
    candidate never opened the file, the second says it opened the wrong one,
    and collapsing them would hide which failure the run actually saw.
    """
    claimed = row.get(field)
    if plural:
        if not isinstance(claimed, list) or any(not isinstance(item, str) for item in claimed):
            return ["surface_digest_missing"]
    elif not isinstance(claimed, str) or not claimed:
        return ["surface_digest_missing"]
    expected = actual if plural else actual[0]
    return [] if claimed == expected else [mismatch]


def register(checkers: dict) -> dict:
    """Add the v2 checker to a registry, leaving every v1 entry untouched."""
    checkers[CHECKER_ID] = documentation_maintenance_v2
    return checkers
