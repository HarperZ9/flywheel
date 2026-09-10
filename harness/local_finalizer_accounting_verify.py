"""Derive counts from planned, bound stage receipts; absence is not zero."""
from __future__ import annotations

from .local_finalizer_accounting import digest
from .local_usage import OLLAMA_USAGE_FIELDS
from .local_finalizer_transport_accounting import transport_counts
from .local_finalizer_experiment import SYSTEMIC_FINALIZER_STATES

SKIPS = {"skipped_candidate_unavailable", "skipped_candidate_ineligible", "skipped_systemic_arm_block"}


def _stage(plan, receipt):
    if any(receipt.get(k) != v for k, v in plan.items()):
        raise ValueError("receipt identity mismatch")
    events = receipt["events"]
    if digest(events) != receipt["events_sha256"]:
        raise ValueError("event digest mismatch")
    starts, terminal, instrumented = {}, {}, False
    disposed = False
    if receipt["disposition"] not in SKIPS | {"returned", "raised"}:
        raise ValueError("unknown stage disposition")
    for ordinal, event in enumerate(events):
        clean = {k: v for k, v in event.items() if k != "event_id"}
        if (type(event["seq"]) is not int or event["seq"] != ordinal or event["stage_id"] != plan["stage_id"]
                or digest(clean) != event["event_id"] or disposed):
            raise ValueError("event sequence or binding invalid")
        kind = event["kind"]
        if kind == "observation_started":
            instrumented = True
        elif kind == "invocation_started":
            identity = event["invocation_id"]
            if (type(event["ordinal"]) is not int or event["ordinal"] != len(starts) + 1 or identity in starts or identity != digest(
                    {"stage_id": plan["stage_id"], "ordinal": event["ordinal"]})):
                raise ValueError("invocation ordinal invalid")
            starts[identity] = event
        elif kind == "invocation_terminal":
            identity = event["invocation_id"]
            if identity not in starts or identity in terminal or event["outcome"] not in {"returned", "raised"}:
                raise ValueError("orphan or duplicate terminal")
            terminal[identity] = event
        elif kind in {"transport", "transport_callable_started", "transport_callable_terminal"}:
            parent = event["invocation_id"]
            if parent is not None and (parent not in starts or parent in terminal):
                raise ValueError("transport parent invalid")
        elif kind == "stage_disposition":
            if event["disposition"] != receipt["disposition"]:
                raise ValueError("stage disposition mismatch")
            disposed = True
        elif kind not in {"runner_entered", "transport_observation_started"}:
            raise ValueError("unknown event kind")
    skip = receipt["disposition"] in SKIPS
    if skip and (plan["stage"] == "normal" or starts or any(e["kind"] == "runner_entered" for e in events)):
        raise ValueError("invoked stage cannot be skipped")
    complete = disposed and (skip or instrumented and len(terminal) == len(starts))
    return starts, terminal, complete


def aggregate_accounting(manifest, receipts):
    plans = {p["stage_id"]: p for p in manifest["stages"]}
    if len(plans) != len(manifest["stages"]):
        raise ValueError("duplicate planned stage")
    groups = {}
    for plan in plans.values():
        if plan["run_id"] != manifest["run_id"]:
            raise ValueError("planned run mismatch")
        groups.setdefault(plan["prefix_id"], []).append(plan["stage"])
    if any(sorted(stages) != ["A", "B", "normal"] for stages in groups.values()):
        raise ValueError("incomplete planned prefix stages")
    found = {}
    for receipt in receipts:
        identity = receipt["stage_id"]
        if identity not in plans:
            raise ValueError("unplanned receipt")
        if identity in found and found[identity] != receipt:
            raise ValueError("conflicting receipt duplicate")
        found[identity] = receipt
    unknown_skip_causes = set()
    plan_order = {identity: index for index, identity in enumerate(plans)}
    for identity, receipt in found.items():
        if receipt["disposition"] not in SKIPS:
            continue
        events = receipt["events"]
        if not events or events[-1]["kind"] != "stage_disposition":
            continue  # incomplete, never assumed a valid zero-call skip
        cause_id = events[-1].get("caused_by")
        if cause_id not in plans or cause_id == identity:
            raise ValueError("skip lacks causal receipt")
        if receipt["disposition"] == "skipped_systemic_arm_block" and (
                plans[cause_id]["stage"] != receipt["stage"] or plan_order[cause_id] >= plan_order[identity]):
            raise ValueError("systemic skip must cite an earlier same-arm stage")
        if cause_id not in found:
            unknown_skip_causes.add(identity)
            continue
        cause = found[cause_id]
        if not cause["events"] or cause["events"][-1]["kind"] != "stage_disposition":
            unknown_skip_causes.add(identity)
            continue
        terminal = cause["events"][-1]
        if receipt["disposition"] == "skipped_systemic_arm_block":
            if cause["stage"] != receipt["stage"] or (cause["disposition"] != "raised"
                    and terminal.get("result_state") not in SYSTEMIC_FINALIZER_STATES):
                raise ValueError("invalid systemic skip cause")
        elif (cause["stage"] != "normal" or cause["prefix_id"] != receipt["prefix_id"]
              or receipt["disposition"] == "skipped_candidate_ineligible" and terminal.get("eligible") is not False
              or receipt["disposition"] == "skipped_candidate_unavailable"
                 and terminal.get("result_state") == "returned"):
            raise ValueError("invalid candidate skip cause")
    known = normal = final = returned = raised = ceiling = 0
    complete = len(found) == len(plans)
    missing_tokens = 0
    unknown_prefix = unknown_finalizer = 0
    usages = []
    wire_complete = True
    sends = connections = responses = 0
    seen_attempts = set()
    for identity, plan in sorted(plans.items()):
        if identity not in found:
            stage_complete = False
        else:
            receipt = found[identity]
            starts, terminal, stage_complete = _stage(plan, receipt)
            stage_complete &= identity not in unknown_skip_causes
            known += len(starts)
            if plan["stage"] == "normal":
                normal += len(starts)
            else:
                final += len(starts)
            for start in starts.values():
                if type(start["max_output_tokens"]) is int and start["max_output_tokens"] >= 0:
                    ceiling += start["max_output_tokens"]
                else:
                    missing_tokens += 1
            returned += sum(e["outcome"] == "returned" for e in terminal.values())
            raised += sum(e["outcome"] == "raised" for e in terminal.values())
            usages.extend(terminal.get(i, {}).get("usage") for i in starts)
            if receipt["disposition"] not in SKIPS:
                wire_ok, sent, connected, received, attempts = transport_counts(receipt["events"], starts)
                if seen_attempts & attempts:
                    raise ValueError("transport attempt reused across stages")
                seen_attempts.update(attempts)
                wire_complete &= wire_ok and stage_complete
                sends += sent
                connections += connected
                responses += received
        if not stage_complete:
            complete = wire_complete = False
            if plan["stage"] == "normal":
                unknown_prefix += 1
            else:
                unknown_finalizer += 1
    usage_totals = {}
    for key in sorted(OLLAMA_USAGE_FIELDS):
        values = [u[key] for u in usages if isinstance(u, dict) and type(u.get(key)) is int and u[key] >= 0]
        usage_totals[key] = {"known_total": sum(values), "observed_invocations": len(values),
            "total": sum(values) if complete and len(values) == known else None}
    return {"schema": "harness.local-finalizer-invocation-accounting/v1", "run_id": manifest["run_id"],
        "manifest_sha256": digest(manifest), "accounting_complete": bool(complete),
        "known_started_invocations": known, "total_started_invocations": known if complete else None,
        "normal_started_invocations": normal, "finalizer_started_invocations": final,
        "returned_invocations": returned, "raised_invocations": raised,
        "outcome_unknown_invocations": known - returned - raised,
        "unknown_prefix_count": unknown_prefix, "unknown_finalizer_count": unknown_finalizer,
        "requested_output_token_ceiling": ceiling if complete and not missing_tokens else None,
        "native_usage": usage_totals, "transport_observation_complete": bool(wire_complete),
        "request_send_attempts": sends if wire_complete else None,
        "connection_attempts": connections if wire_complete else None,
        "http_responses": responses if wire_complete else None,
        "does_not_prove": "Invocation and send observations do not prove receiver effects, token use or task correctness."}
