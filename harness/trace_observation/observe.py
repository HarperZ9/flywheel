"""observe.py -- one run end to end: capture, measured gap, receipts, report, hold.

observe_run() takes the provider responses a run already received, captures
the documented reasoning signals, builds the run's measured-gap record, runs
the control bank, writes both as observation receipts into the monitor home's
chain, and raises a hold for each finding. render_report() prints the per-model
report with the observed results, the outside gaps and the local gaps in
separate lists, so a provider limit is never mistaken for unfinished work.
"""
from __future__ import annotations

from . import controls, monitor_hook
from .access_gap import measured_gap
from .adapters import capture
from .receipt import ObservationLedger, build_receipt

CONTROLS_DOES_NOT_PROVE = (
    "The bank shows the instruments return known answers on planted inputs. It does not "
    "check label quality or bound misses on cases nobody planted.")


def observe_run(home, *, run_id: str, provider: str, turns: list, observed_on: str,
                served_model_verdict: str = "UNVERIFIABLE", raise_holds: bool = True,
                extra_findings: list | None = None) -> dict:
    """turns: [{"request": {...}, "response": {...}}] in order."""
    caps = [capture(provider, t.get("request") or {}, t["response"], run_id=run_id, turn_index=i)
            for i, t in enumerate(turns)]
    gap = measured_gap(provider, caps, run_id=run_id, observed_on=observed_on)
    served = sorted({c.record.served_model for c in caps if c.record.served_model})
    subject = {"provider": provider, "served_model": ",".join(served) or "unreported",
               "smp_verdict": served_model_verdict,
               "model_field": ",".join(served) if served_model_verdict == "MATCH" else "unverified",
               "access_classes": gap["access_classes"]}
    ledger = ObservationLedger(home)
    gap_seal = ledger.append(build_receipt(
        run_id=run_id, component="measured-gap", subject=subject,
        inputs={"turns": str(len(caps)),
                "records": [c.record.to_dict() for c in caps]},
        result={"verdict": "DRIFT" if gap["documentation_drift"] else "RECORDED",
                "fields": gap["fields"], "documentation_drift": gap["documentation_drift"],
                "built_on": gap["built_on"]},
        gaps=gap["not_observable_from_outside"] + gap["not_yet_observed_local"],
        does_not_prove=gap["does_not_prove"]))
    bank = controls.run_bank()
    bank_seal = ledger.append(build_receipt(
        run_id=run_id, component="control-bank", subject=subject, inputs={},
        controls=bank, result={"verdict": "PASS" if all(c["passed"] == "true" for c in bank)
                               else "CONTROL_FAILED"},
        gaps=[], does_not_prove=CONTROLS_DOES_NOT_PROVE))
    findings = (monitor_hook.findings_from_measured_gap(gap)
                + monitor_hook.findings_from_controls("control-bank", bank)
                + list(extra_findings or []))
    holds = monitor_hook.raise_holds(home, run_id, findings, subject=subject) if raise_holds else []
    return {"captures": caps, "measured_gap": gap, "receipts": [gap_seal, bank_seal],
            "controls": bank, "findings": findings, "holds": holds, "subject": subject}


def render_report(result: dict, observed: dict | None = None) -> str:
    gap, subj = result["measured_gap"], result["subject"]
    lines = [f"model: {subj['served_model']} (SMP: {subj['smp_verdict']})",
             f"provider: {gap['provider']}   access: {', '.join(gap['access_classes']) or 'A0'}",
             "observed:"]
    for name, verdict in (observed or {}).items():
        lines.append(f"  {name}: {verdict}")
    for f in gap["fields"]:
        if f["agreement"] != "DOCUMENTED_ONLY":
            lines.append(f"  {f['field']}: documented {f['documented']}, observed {f['observed']}"
                         f" -> {f['agreement']}")
    lines.append("not observable from outside:")
    for g in gap["not_observable_from_outside"] or [{"component": "(none recorded)", "gap_code": ""}]:
        lines.append(f"  {g['component']} .... {g['gap_code']}  {g.get('evidence', '')}".rstrip())
    lines.append("not yet observed (local work):")
    for g in gap["not_yet_observed_local"] or [{"component": "(none recorded)", "gap_code": ""}]:
        lines.append(f"  {g['component']} .... {g['gap_code']}".rstrip())
    lines.append(f"holds raised: {len(result['holds'])}")
    lines.append("does not prove: " + gap["does_not_prove"])
    return "\n".join(lines)
