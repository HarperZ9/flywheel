"""Freeze pipeline for the redaction-contract family.

Moved verbatim out of generate.py to keep each generation module under the
size gate; generate.py re-exports these names so callers and tests are
unaffected.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from verifiers_component_forge.families import redaction_contract as red


def build_redaction_contract() -> dict:
    out: dict[str, dict] = {}
    for variant in red.all_variants():
        rows = []
        for fixture in red.fixtures_for(variant):
            rows.append(
                {
                    "cell": fixture["cell"],
                    "record": fixture["record"],
                    "expect": red.reference_redact(fixture["record"]),
                }
            )
        out[variant.variant_id] = {
            "variant": {
                "title": variant.title,
                "purpose": variant.purpose,
            },
            "worked": red.worked_for(variant),
            "fixtures": rows,
        }
    return out


def _declared_raw_secret_values(record: dict) -> list[str]:
    rows = record.get("secrets") or []
    values = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        raw = item.get("value")
        if isinstance(raw, str) and raw:
            values.append(raw)
    return values


def assert_redaction_expected_safe(data: dict) -> int:
    """Fail closed if any expected output contains a declared raw secret.

    The scan derives raw values from each row's own ``record['secrets']``
    declarations, so it catches non-standard synthetic values as well as the
    standard ``FAKE_SECRET_DO_NOT_USE_LOOP29`` marker family.
    """
    checked_values = 0
    for variant_id, entry in sorted(data.items()):
        if not isinstance(entry, dict):
            raise ValueError(f"{variant_id}: redaction entry must be a dict")  # noqa: TRY004 -- data validation, tests pin ValueError
        for section in ("fixtures", "worked"):
            rows = entry.get(section)
            if not isinstance(rows, list):
                raise ValueError(f"{variant_id}: {section} must be a list")  # noqa: TRY004 -- data validation, tests pin ValueError
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError(f"{variant_id}/{section}: row must be a dict")  # noqa: TRY004 -- data validation, tests pin ValueError
                cell = row.get("cell", "<unknown>")
                record = row.get("record")
                if not isinstance(record, dict):
                    raise ValueError(  # noqa: TRY004 -- data validation, tests pin ValueError
                        f"{variant_id}/{section}/{cell}: record must be a dict"
                    )
                expected = json.dumps(
                    row.get("expect"), sort_keys=True, ensure_ascii=True
                )
                for raw in _declared_raw_secret_values(record):
                    checked_values += 1
                    if raw in expected:
                        raise ValueError(
                            "declared raw secret leaked into expected JSON at "
                            f"{variant_id}/{section}/{cell}"
                        )
    return checked_values
