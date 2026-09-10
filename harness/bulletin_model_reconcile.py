"""Read only the fixed study's pinned receipts; counts never prove delivery."""
from __future__ import annotations

import hashlib
import math
import re
from types import SimpleNamespace
from uuid import UUID

from .bulletin_model_budget import generation_plan
from .bulletin_model_call import _accepted_backend_result
from .bulletin_model_worker import _validate
from .evidence_json import canonical_bytes, strict_load_json
from .local_agent import OllamaBackend
from .local_usage import OLLAMA_USAGE_FIELDS, ollama_native_usage
from .private_artifact_fs import PrivateArtifactError, NOT_FOUND


def _need(value):
    if not value:
        raise ValueError("receipt_mismatch")


def _version(row):
    _need(type(row) is dict and type(row.get("schema_version")) is int and row["schema_version"] == 1)


class _Read:
    def __init__(self):
        self.hashes = []

    def __call__(self, store, name, scope, *, cap=8192, optional=False, sha=None, parse=True):
        try:
            raw = store.read(name, max_bytes=cap, expected_sha256=sha)
        except Exception as exc:
            cause = exc
            while cause is not None:
                if optional and isinstance(cause, PrivateArtifactError) and cause.code == NOT_FOUND:
                    return None
                cause = cause.__cause__
            raise ValueError("receipt_unavailable") from None
        self.hashes.append({"scope": scope, "record_name": name, "sha256": hashlib.sha256(raw).hexdigest()})
        return strict_load_json(raw, max_bytes=cap, max_depth=24) if parse else raw


def _request_body(req):
    """Use the existing pure serializer; no transport is installed or called."""
    readiness = req["stage_id"] == "readiness"
    backend = OllamaBackend(base_url=req["profile"]["endpoint_url"], model=req["profile"]["selectors"][0],
        num_ctx=req["profile"]["generation_config"]["num_ctx"], transport=None)
    # probe_profile owns this fixed system instruction and temperature.
    _, raw = backend._body(req["messages"], "You are running a bounded local endpoint gate." if readiness else
        req["system"], req["max_tokens"], 0.0 if readiness else req["temperature"], req["seed"], False)
    return strict_load_json(raw, max_bytes=262144, max_depth=16)


def _ledger(read, store, refs, run_id, reserved, terminals):
    _need(type(refs) is list and 1 <= len(refs) <= 100)
    active, previous, continued, writes, stopped = None, -1, False, set(), False
    plan = generation_plan()
    for ordinal, ref in enumerate(refs):
        _need(type(ref) is dict and set(ref) == {"record_name", "sha256"}
              and ref["record_name"] == f"ledger-{ordinal:04d}.json"
              and type(ref["sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", ref["sha256"]))
        row = read(store, ref["record_name"], "ledger", sha=ref["sha256"], cap=32768)
        _need(row["schema"] == "flywheel.bulletin-model-ledger/v1" and row["run_id"] == run_id
              and type(row["ordinal"]) is int and row["ordinal"] == ordinal)
        kind = row["kind"]
        extra = {"manifest": {"planned"}, "generation_reserved": {"reservation_id", "stage_id", "max_tokens"},
            "generation_terminal": {"reservation_id", "outcome"}, "continuation": {"gate_record_sha256"},
            "write_reserved": {"reservation_id", "slot_id", "operation_sha256"}}
        _need(kind in extra and set(row) == {"schema", "run_id", "ordinal", "kind"} | extra[kind])
        if ordinal == 0:
            _need(kind == "manifest" and row["planned"] == plan)
        elif kind == "generation_reserved":
            stage = row["stage_id"]
            index = next(i for i, item in enumerate(plan) if item["stage_id"] == stage)
            _need(not stopped and active is None and stage not in reserved and index > previous
                  and (index == previous + 1 if previous < 1 or index >= 2 and (index - 2) % 3 else True)
                  and (index < 14 or continued)
                  and row["reservation_id"] == f"{run_id}-{stage}"
                  and type(row["max_tokens"]) is int and row["max_tokens"] == plan[index]["max_tokens"])
            reserved[stage], active, previous = row, stage, index
        elif kind == "generation_terminal":
            _need(active is not None and row["reservation_id"] == reserved[active]["reservation_id"]
                  and row["outcome"] in ("response_received", "no_send", "unknown"))
            terminals[active], active = row["outcome"], None
            stopped = row["outcome"] != "response_received"
        else:
            _need(kind in ("continuation", "write_reserved") and active is None)
            if kind == "continuation":
                _need(not continued and previous >= 11 and type(row["gate_record_sha256"]) is str
                      and re.fullmatch(r"[a-f0-9]{64}", row["gate_record_sha256"]))
                continued = True
            else:
                slot = row["slot_id"]
                _need(slot in {f"s{i:02d}" for i in range(1, 13 if continued else 5)} and slot not in writes
                      and terminals.get(slot + "-p2") == "response_received" and row["reservation_id"] == f"{run_id}-{slot}-write"
                      and type(row["operation_sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", row["operation_sha256"]))
                writes.add(slot)


def _events(read, store, stage, run_id, rid, counters, seen_ids):
    attempts, routes, missing = {}, {}, False
    for index in range(6):
        row = read(store, f"transport-{index:03d}.json", stage, cap=4096, optional=True)
        if row is None:
            missing = True
            continue
        _version(row)
        _need(not missing and set(row) == {"schema_version", "run_id", "reservation_id", "stage_id", "index", "event"}
              and row["run_id"] == run_id and row["reservation_id"] == rid and row["stage_id"] == stage
              and type(row["index"]) is int and row["index"] == index)
        event = row["event"]
        _need(type(event) is dict and set(event) == {"attempt_id", "method", "path", "phase",
            "connection_started", "request_send_started", "outcome", "code", "status"})
        aid, phase = event["attempt_id"], event["phase"]
        _need(str(UUID(aid)) == aid)
        route = (event["method"], event["path"])
        _need(route == ("POST", "/api/chat") or stage == "readiness" and route == ("GET", "/api/tags"))
        previous = attempts.get(aid)
        if previous is None:
            _need(aid not in seen_ids and route not in routes and all(e["phase"] == "terminal" for e in routes.values()))
            _need(route[0] != "GET" or not routes)
            seen_ids.add(aid)
        _need((phase == "connection_attempt" and previous is None) or
            (phase == "request_send_started" and previous == (route, "connection_attempt")) or
            (phase == "terminal" and previous in (None, (route, "connection_attempt"), (route, "request_send_started"))))
        connected, sent = event["connection_started"], event["request_send_started"]
        _need(type(connected) is bool and type(sent) is bool)
        if phase != "terminal":
            _need(event["outcome"] is None and event["code"] is None and event["status"] is None
                  and sent is False and connected == (phase == "request_send_started"))
        else:
            _need(event["outcome"] in ("response", "error", "timeout") and type(event["code"]) is str
                  and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", event["code"])
                  and (event["status"] is None or type(event["status"]) is int and 100 <= event["status"] <= 599)
                  and (not sent or connected) and (previous is not None or not (connected or sent)))
            _need(not sent or previous == (route, "request_send_started"))
            _need(previous != (route, "request_send_started") or connected)
            _need(event["outcome"] != "response" or event["code"] == "response_received"
                  and type(event["status"]) is int and sent)
        count = counters["health" if route[0] == "GET" else "generation"]
        count["attempts_observed"] += previous is None
        count["connection_intents"] += phase == "connection_attempt"
        count["send_intents"] += phase == "request_send_started"
        count["terminals"] += phase == "terminal"
        count["response_terminals"] += phase == "terminal" and event["outcome"] == "response"
        count["send_progressions"] += phase == "terminal" and sent
        attempts[aid] = (route, phase)
        routes[route] = event
    _need(all(phase == "terminal" for _, phase in attempts.values()))
    return routes


def _invocation(read, ledger, store, reservation, terminal, report, seen_ids):
    stage, rid = reservation["stage_id"], reservation["reservation_id"]
    launch = read(store, "worker-launch.json", stage, cap=147456)
    _version(launch)
    _need(set(launch) == {"schema_version", "request", "request_sha256", "exchange_path", "exchange_identity", "reservation_record"})
    req = launch["request"]
    _validate(req, reservation)
    sha = hashlib.sha256(canonical_bytes(req)).hexdigest()
    _need(launch["request_sha256"] == sha and canonical_bytes(launch["reservation_record"]) == canonical_bytes(reservation)
          and canonical_bytes(launch["exchange_identity"]) == canonical_bytes(store.identity.to_json_dict())
          and launch["exchange_path"] == str(store.path))
    claim = read(ledger, "worker-claim-" + hashlib.sha256(rid.encode("ascii")).hexdigest()[:32] + ".json", "ledger")
    _need(claim == {"schema_version": 1, "reservation_id": rid, "request_sha256": sha,
                    "exchange_identity": launch["exchange_identity"]})
    _version(claim)
    started = read(store, "worker-started.json", stage)
    _version(started)
    _need(started == {"schema_version": 1, "request_sha256": sha})
    report["worker_starts_observed"] += 1
    routes = _events(read, store, stage, req["run_id"], rid, report["transport"], seen_ids)
    _need(stage != "readiness" or ("GET", "/api/tags") in routes)
    usage, captured, captured_text = None, False, None
    for method, path, prefix in (("GET", "/api/tags", "health-"), ("POST", "/api/chat", "")):
        request = read(store, prefix + "request.json", stage, optional=True)
        capture = read(store, prefix + "response.json", stage, cap=2097152, optional=True)
        event = routes.get((method, path))
        _need((request is not None) == (event is not None))
        if request is None:
            _need(capture is None)
            continue
        _need(set(request) == {"reservation_id", "stage_id", "method", "url", "timeout_seconds", "generation_max_tokens"}
              and request["reservation_id"] == rid and request["stage_id"] == stage and request["method"] == method
              and request["url"] == req["profile"]["endpoint_url"] + path
              and type(request["timeout_seconds"]) in (int, float) and math.isfinite(request["timeout_seconds"])
              and 0 < request["timeout_seconds"] <= (5 if method == "GET" else 60))
        if method == "POST":
            body = read(store, "request.bin", stage, cap=262144)
            _need(type(request["generation_max_tokens"]) is int and request["generation_max_tokens"] == req["max_tokens"]
                  and canonical_bytes(body) == canonical_bytes(_request_body(req)))
        else:
            _need(request["generation_max_tokens"] is None)
        if capture is None:
            _need(event["outcome"] != "response")
            continue
        _need(set(capture) == {"reservation_id", "stage_id", "capture_kind", "status", "parsed_response", "assistant_text_state", "usage"}
              and capture["reservation_id"] == rid and capture["stage_id"] == stage
              and capture["capture_kind"] == "parsed_response_not_wire" and type(capture["status"]) is int
              and event["outcome"] == "response" and event["status"] == capture["status"])
        if method == "POST":
            parsed = capture["parsed_response"]
            message = parsed.get("message") if type(parsed) is dict else None
            text = message.get("content") if type(message) is dict else None
            captured_text = text if type(text) is str else None
            _need(capture["assistant_text_state"] == ("available" if type(text) is str else "invalid_or_missing"))
            assistant = read(store, "assistant.txt", stage, cap=1048576, optional=True, parse=False)
            _need(assistant == (text.encode("utf-8", "strict") if type(text) is str else None))
            usage = ollama_native_usage(parsed) if type(parsed) is dict else None
            _need(canonical_bytes(capture["usage"]) == canonical_bytes(usage))
            captured = True
            report["response_captures"] += 1
    process = read(store, "worker-process.json", stage)
    _version(process)
    _need(set(process) == {"schema_version", "reservation_id", "timed_out", "returncode", "elapsed_ms", "malformed_output"}
          and process["reservation_id"] == rid and process["timed_out"] is False
          and type(process["returncode"]) is int and process["returncode"] == 0
          and type(process["elapsed_ms"]) is int and process["elapsed_ms"] >= 0 and process["malformed_output"] is False)
    saved = read(store, "worker-result.json", stage, cap=2097152)
    _version(saved)
    _need(set(saved) == {"schema_version", "request_sha256", "reservation_id", "result"}
          and saved["request_sha256"] == sha and saved["reservation_id"] == rid)
    result = saved["result"]
    _need(type(result) is dict and set(result) == {"outcome", "backend_valid", "text", "failure", "backend_result"}
          and type(result["backend_valid"]) is bool and result["outcome"] == terminal
          and (result["text"] is None or type(result["text"]) is str) and result["text"] == captured_text)
    _need(terminal == "response_received" and captured or terminal == "no_send" and
          ("POST", "/api/chat") not in routes and result["backend_valid"] is False and result["text"] is None)
    backend = result["backend_result"]
    accepted, _ = _accepted_backend_result(backend, SimpleNamespace(model=req["profile"]["selectors"][0],
        stage_id=stage, health_entered=("GET", "/api/tags") in routes), captured_text)
    _need(result["backend_valid"] == (result["failure"] is None and type(captured_text) is str and accepted))
    if type(backend) is dict and "generation_config" in backend:
        _need(canonical_bytes(backend["generation_config"]) == canonical_bytes(_request_body(req)["options"]))
    return usage if captured else {key: 0 for key in OLLAMA_USAGE_FIELDS}


def reconcile_generation_accounting(*, run_id, ledger, ledger_refs, invocations):
    """A closed-prefix snapshot; missing evidence is a gap, never a retry permit.

    The parent supplies all sealed ledger refs and retained invocation custody.
    This does not inventory unrelated host activity or measure provider billing.
    """
    plan, read = generation_plan(), _Read()
    report = {"schema": "flywheel.bulletin-model-accounting/v1", "run_id": run_id,
        "reconciled": False, "gaps": [], "planned_generations": len(plan),
        "planned_output_token_ceiling": sum(item["max_tokens"] for item in plan),
        "reserved_generations": 0, "requested_output_tokens": 0, "worker_starts_observed": 0,
        "response_captures": 0, "unknown_generation_terminals": 0, "missing_generation_terminals": 0,
        "transport": {kind: dict.fromkeys(("attempts_observed", "connection_intents", "send_intents",
            "terminals", "response_terminals", "send_progressions"), 0) for kind in ("health", "generation")},
        "native_usage": {}, "delivery_count": None, "record_hashes": read.hashes, "invocations": [],
        "counts_scope": "Validated persisted receipts only; intents and responses do not prove delivery."}
    reserved, terminals, usages, seen_ids = {}, {}, [], set()
    ledger_valid = False
    try:
        _need(type(run_id) is str and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", run_id))
        _ledger(read, ledger, ledger_refs, run_id, reserved, terminals)
        ledger_valid = True
        _need(type(invocations) is dict and not set(invocations) - set(reserved))
    except Exception:
        report["gaps"].append({"scope": "ledger", "code": "ledger_or_inventory_invalid"})
    report["reserved_generations"] = len(reserved) if ledger_valid else None
    report["requested_output_tokens"] = sum(row["max_tokens"] for row in reserved.values()) if ledger_valid else None
    unknown = sum(value == "unknown" for value in terminals.values())
    report["unknown_generation_terminals"] = unknown if ledger_valid else None
    report["missing_generation_terminals"] = len(reserved) - len(terminals) if ledger_valid else None
    report["validated_ledger_prefix"] = {"reservations": len(reserved), "unknown_terminals": unknown}
    for stage, reservation in reserved.items():
        row = {"stage_id": stage, "reservation_id": reservation["reservation_id"],
               "terminal": terminals.get(stage), "receipt_status": "incomplete"}
        report["invocations"].append(row)
        try:
            usages.append(_invocation(read, ledger, invocations[stage], reservation, terminals.get(stage), report, seen_ids))
            row["receipt_status"] = "reconciled"
        except Exception:
            report["gaps"].append({"scope": stage, "code": "invocation_unreconciled"})
    report["reconciled"] = not report["gaps"]
    for field in sorted(OLLAMA_USAGE_FIELDS):
        values = [(u or {}).get(field) for u in usages]
        valid = [v for v in values if type(v) is int and v >= 0]
        complete = report["reconciled"] and len(valid) == len(reserved)
        report["native_usage"][field] = {"total": sum(valid) if complete else None,
            "covered_invocations": len(valid), "required_invocations": len(reserved) if ledger_valid else None}
    return report
