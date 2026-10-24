"""receipt.py -- the one receipt every deterministic check returns."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

SCHEMA_V1 = "flywheel.check-receipt/v1"
SCHEMA = "flywheel.check-receipt/v2"  # v2 names `scope`
PASS, FAIL, UNVERIFIABLE = "PASS", "FAIL", "UNVERIFIABLE"
SCOPE = ("A passing check shows the subject has the checked structure or value. "
         "Whether the subject is right in meaning is a separate review.")


def digest(value) -> str:
    """sha256 of canonical JSON; non-JSON values hash by their repr."""
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        data = repr(value)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CheckReceipt:
    check: str
    verdict: str
    code: str
    reason: str
    subject_sha256: str
    spec_sha256: str
    schema: str = SCHEMA
    scope: str = SCOPE

    @property
    def passed(self) -> bool:
        return self.verdict == PASS

    def to_dict(self) -> dict:
        return asdict(self)
