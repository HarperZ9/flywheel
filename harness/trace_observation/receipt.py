"""receipt.py -- flywheel.observation-receipt/v1, written into the monitor's sealed chain.

The trace-observation layer and the pre-action monitor share one receipt path:
an observation receipt is appended to the same records.jsonl a monitor home
keeps for holds, allows and decisions, through the same fail-closed writer.
That store chains every record by prev_record_sha256 and a sequence number and
seals it with sha256 over canonical bytes, so `flywheel monitor verify` re-walks
observations and holds together, and a trace flag can cite the receipt that
raised it.

Field order follows MODULE-DESIGN section 7. No floats: counts are digit
strings, interval bounds are four-place decimal strings, booleans are
"true"/"false". Reasoning text never enters a receipt, only its digest.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..preaction.records import HoldStore, verify_seal

SCHEMA = "flywheel.observation-receipt/v1"
COMPONENT_VERSION = "0.1.0"


class FloatInReceipt(ValueError):
    """A float reached a receipt; the v1 contract allows strings and integers only."""


def _no_floats(value, path="receipt") -> None:
    if isinstance(value, float):
        raise FloatInReceipt(f"{path} is a float ({value!r}); format it with intervals.fmt4")
    if isinstance(value, dict):
        for k, v in value.items():
            _no_floats(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _no_floats(v, f"{path}[{i}]")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_receipt(*, run_id: str, component: str, subject: dict, inputs: dict, result: dict,
                  gaps: list, does_not_prove: str, controls: list | None = None,
                  readout_provenance: dict | None = None, flywheel_revision: str = "unrecorded",
                  probe_blob_sha: dict | None = None, started_utc: str = "",
                  finished_utc: str = "") -> dict:
    """One observation receipt in fixed field order. Chain and seal come at append."""
    rec = {
        "schema": SCHEMA,
        "source": f"observation:{run_id}:{component}",
        "run_id": run_id,
        "component": component,
        "component_version": COMPONENT_VERSION,
        "flywheel_revision": flywheel_revision,
        "probe_blob_sha": dict(probe_blob_sha or {}),
        "subject": dict(subject),
        "inputs": dict(inputs),
        "readout_provenance": dict(readout_provenance or {}),
        "controls": list(controls or []),
        "result": dict(result),
        "gaps": [g.to_dict() if hasattr(g, "to_dict") else dict(g) for g in gaps],
        "does_not_prove": does_not_prove,
        "started_utc": started_utc or utc_now(),
        "finished_utc": finished_utc or utc_now(),
    }
    _no_floats(rec)
    return rec


class ObservationLedger:
    """Observation receipts in a monitor home's chain. Fails closed like the monitor."""

    def __init__(self, home) -> None:
        self.store = HoldStore(home)

    def append(self, receipt: dict) -> str:
        if receipt.get("schema") != SCHEMA:
            raise ValueError("ObservationLedger.append: not an observation receipt")
        _no_floats(receipt)
        return self.store.append(dict(receipt))

    def receipts(self, run_id: str | None = None) -> list:
        return [r for r in self.store.read_all(tolerant=True)
                if r.get("schema") == SCHEMA and (run_id is None or r.get("run_id") == run_id)]

    def verify(self, seal_hex: str) -> bool:
        for r in self.receipts():
            if r.get("seal", {}).get("hex") == seal_hex:
                return verify_seal(r)
        return False
