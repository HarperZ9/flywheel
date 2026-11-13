"""why_gate.py -- `flywheel why` for the record `flywheel gate` writes.

`flywheel gate` seals a proof envelope (gate_envelope.json) and a step report
(gate_report.json). That envelope is a different record from a signed receipt,
so `flywheel why` used to answer "not a receipt envelope" for the file the
neighbouring command had just written. This reader answers from those two
files with the same rules as why.py: nothing is recomputed against the oracle,
what would change the answer comes before what decided it, and how far the
record reaches is part of the answer.
"""
from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

from .envelope import ProofEnvelope

ENVELOPE_NAME = "gate_envelope.json"
REPORT_NAME = "gate_report.json"
_REQUIRED = ("task_id", "candidate", "oracle", "oracle_cmd", "oracle_output_hash",
             "verdict", "model_ref", "seed", "prompt_hash", "budget_spent")


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _envelope(data) -> "ProofEnvelope | None":
    if not isinstance(data, dict) or "receipt" in data:
        return None
    if any(key not in data for key in _REQUIRED):
        return None
    known = {f.name for f in fields(ProofEnvelope)}
    try:
        return ProofEnvelope(**{k: v for k, v in data.items() if k in known})
    except TypeError:
        return None


def _report_state(report, envelope: ProofEnvelope) -> dict:
    """Whether the step report beside the envelope still names this envelope."""
    if not isinstance(report, dict):
        return {"present": False, "agrees": False, "rewitness": "not recorded"}
    agrees = (report.get("envelope_hash") == envelope.content_hash()
              and report.get("claim_hash") == envelope.claim_hash()
              and report.get("verdict") == envelope.verdict)
    return {"present": True, "agrees": agrees,
            "rewitness": str(report.get("rewitness", "not recorded"))}


def explain(target) -> "dict | None":
    """The answer for a gate envelope file, or for a folder that holds one.
    None when `target` is not a gate record, so the caller keeps its own error."""
    target = Path(target)
    path = target / ENVELOPE_NAME if target.is_dir() else target
    envelope = _envelope(_read(path)) if path.is_file() else None
    if envelope is None:
        return None
    return {
        "kind": "gate", "record": str(path), "verdict": envelope.verdict,
        "task_id": envelope.task_id, "oracle": envelope.oracle,
        "oracle_cmd": envelope.oracle_cmd, "model_ref": envelope.model_ref,
        "oracle_output_hash": envelope.oracle_output_hash,
        "oracle_excerpt": envelope.oracle_stdout_excerpt,
        "subject": envelope.content_hash(), "claim": envelope.claim_hash(),
        "budget_spent": dict(envelope.budget_spent or {}),
        "report": _report_state(_read(path.with_name(REPORT_NAME)), envelope),
    }


def _report_line(report: dict) -> str:
    if not report["present"]:
        return f"no {REPORT_NAME} beside it, so no re-run is on record"
    if not report["agrees"]:
        return (f"{REPORT_NAME} names a different envelope: DRIFT between the "
                "two files, so one of them changed after the gate ran")
    return (f"{REPORT_NAME} names this envelope; the gate's own re-run "
            f"recorded {report['rewitness']}")


def render(e: dict) -> str:
    calls = e["budget_spent"].get("oracle_calls", "an unrecorded number of")
    lines = [
        f"{e['verdict']} on {e['task_id']} (gate record, unsigned)",
        f"record {e['record']}",
        f"subject {e['subject']}  claim {e['claim']}",
        "",
        "what would change it:",
        f"  - a different candidate: the oracle {e['oracle']} checks the stored "
        "candidate exactly, so any edit to it changes the subject digest",
        f"  - a different oracle or oracle command: this used {e['oracle_cmd']}",
        "  - an edit to either file: the report beside this envelope holds the "
        "digests and the result of the gate's own second oracle run",
        "",
        "what decided it:",
        f"  oracle     {e['oracle']} ({e['oracle_cmd']})",
        f"  output     {e['oracle_output_hash']}  {e['oracle_excerpt']}".rstrip(),
        f"  proposer   {e['model_ref']}",
        f"  cost       {calls} oracle call(s)",
        f"  re-run     {_report_line(e['report'])}",
        "",
        "scope:",
        "  - read from the files; the oracle was not run again to answer this",
        "  - a gate record carries no signature, so it shows what this "
        "machine wrote and nothing a third party can check without re-running",
        "  - the gate uses a built-in task with a fixed proposer; it shows the "
        "pipeline works end to end and says nothing about a model",
    ]
    return "\n".join(lines)
