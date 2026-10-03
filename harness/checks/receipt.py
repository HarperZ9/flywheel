"""receipt.py -- the one receipt every deterministic check returns."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

SCHEMA = "flywheel.check-receipt/v1"
PASS, FAIL, UNVERIFIABLE = "PASS", "FAIL", "UNVERIFIABLE"
DOES_NOT_PROVE = ("A passing check shows the subject has the checked structure or value. "
                  "It does not show the subject is right in meaning.")


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
    does_not_prove: str = DOES_NOT_PROVE

    @property
    def passed(self) -> bool:
        return self.verdict == PASS

    def to_dict(self) -> dict:
        return asdict(self)
