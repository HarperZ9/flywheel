"""One-generation child and Windows owned-job supervisor; no resume or retry."""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import re
import sys
import time
from uuid import UUID

from .bulletin_model_call import OneGenerationTransport, execute_backend_once
from .bulletin_model_exchange import PrivateExchange
from .cross_harness_process import start_owned_process
from .evidence_json import canonical_bytes, strict_load_json
from .local_agent import OllamaBackend
from .model_endpoint_gate_cli import probe_profile
from .private_artifact_fs import ArtifactIdentity
from .strict_local_http import StrictLocalHTTPPolicy, make_strict_local_http


class WorkerError(RuntimeError):
    pass


def _require(condition):
    if not condition:
        raise WorkerError("worker_input_invalid")


def _id(value):
    return type(value) is str and bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", value))


def _seconds(value, cap):
    return type(value) in (int, float) and math.isfinite(value) and 0 < value <= cap


def _validate(request, reservation):
    try:
        _require(type(request) is dict and set(request) == {"schema_version", "run_id", "reservation_id",
            "stage_id", "profile", "system", "messages", "seed", "temperature", "max_tokens", "timeout_seconds"})
        _require(type(request["schema_version"]) is int and request["schema_version"] == 1)
        _require(all(_id(request[key]) for key in ("run_id", "reservation_id", "stage_id")))
        stage = request["stage_id"]
        ceiling = 32 if stage == "readiness" else 256 if stage == "smoke" else 512
        _require(stage in ("readiness", "smoke") or bool(re.fullmatch(r"s(?:0[1-9]|1[0-2])-p[1-3]", stage)))
        _require(type(request["max_tokens"]) is int and request["max_tokens"] == ceiling)
        _require(type(request["seed"]) is int and 0 <= request["seed"] <= 2147483647)
        temp = request["temperature"]
        _require(type(temp) in (float, int) and math.isfinite(temp) and 0 <= temp <= 2)
        _require(_seconds(request["timeout_seconds"], 60) and type(request["system"]) is str)
        messages = request["messages"]
        _require(type(messages) is list and 1 <= len(messages) <= 16)
        _require(all(type(m) is dict and set(m) == {"role", "content"} and
            m["role"] in ("user", "assistant") and type(m["content"]) is str for m in messages))
        if stage == "readiness":
            _require(len(messages) == 1 and messages[0]["role"] == "user" and request["system"] == "" and temp == 0)
        profile = request["profile"]
        required = {"profile_id", "backend", "endpoint_url", "selectors", "model_ref",
                    "expected_ollama_digest", "generation_config"}
        _require(type(profile) is dict and required <= set(profile) and not set(profile) - required -
            {"schema", "model", "model_key", "provider_role", "release_asset_sha256"})
        _require(all(type(profile[key]) is str and len(profile[key]) <= 256 for key in set(profile) - required))
        _require(profile["backend"] == "ollama" and _id(profile["profile_id"]))
        selectors = profile["selectors"]
        _require(type(selectors) is list and len(selectors) == 1 and type(selectors[0]) is str)
        _require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", selectors[0])))
        _require(not selectors[0].startswith("ollama:") and profile["model_ref"] == "ollama:" + selectors[0])
        _require(type(profile["expected_ollama_digest"]) is str and bool(re.fullmatch(
            r"(?:sha256:)?[0-9a-f]{64}", profile["expected_ollama_digest"])))
        config = profile["generation_config"]
        _require(type(config) is dict and set(config) == {"num_ctx"} and type(config["num_ctx"]) is int
                 and 1 <= config["num_ctx"] <= 1048576)
        _require(len(canonical_bytes(request)) <= 131072)
        _require(type(reservation) is dict and set(reservation) == {"schema", "kind", "ordinal", "run_id",
            "reservation_id", "stage_id", "max_tokens"} and reservation["schema"] == "flywheel.bulletin-model-ledger/v1"
            and reservation["kind"] == "generation_reserved" and type(reservation["ordinal"]) is int
            and reservation["ordinal"] >= 1)
        _require(all(type(reservation[k]) is type(request[k]) and reservation[k] == request[k]
                     for k in ("run_id", "reservation_id", "stage_id", "max_tokens")))
        routes = frozenset({("POST", "/api/chat")} | ({("GET", "/api/tags")} if stage == "readiness" else set()))
        return StrictLocalHTTPPolicy(profile["endpoint_url"], routes, max_timeout_seconds=request["timeout_seconds"])
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError) as exc:
        raise WorkerError("worker_input_invalid") from exc


def run_worker(request, store, reservation, *, transport_factory=make_strict_local_http):
    policy = _validate(request, reservation)
    index, attempts = 0, {}
    def observe(event):
        nonlocal index
        _require(type(event) is dict and set(event) == {"attempt_id", "method", "path", "phase",
            "connection_started", "request_send_started", "outcome", "code", "status"} and index < 6)
        _require(str(UUID(event["attempt_id"])) == event["attempt_id"])
        route = (event["method"], event["path"])
        _require(route in policy.allowed_routes and all(type(event[k]) is bool for k in
            ("connection_started", "request_send_started")))
        phase, previous = event["phase"], attempts.get(event["attempt_id"])
        _require((phase == "connection_attempt" and previous is None) or
                 (phase == "request_send_started" and previous == (route, "connection_attempt")) or
                 (phase == "terminal" and previous in (None, (route, "connection_attempt"), (route, "request_send_started"))))
        _require(event["outcome"] in (None, "response", "error", "timeout") and
                 (event["code"] is None or _id(event["code"])) and
                 (event["status"] is None or type(event["status"]) is int and 100 <= event["status"] <= 599))
        if phase != "terminal":
            _require(event["outcome"] is None and event["code"] is None and event["status"] is None
                     and event["request_send_started"] is False
                     and event["connection_started"] == (phase == "request_send_started"))
        else:
            _require(event["outcome"] is not None and _id(event["code"])
                     and (not event["request_send_started"] or event["connection_started"]))
            _require(previous is not None or not (event["connection_started"] or event["request_send_started"]))
            _require(event["outcome"] != "response" or (event["code"] == "response_received"
                     and type(event["status"]) is int and event["request_send_started"]))
        store.put(f"transport-{index:03d}.json", canonical_bytes({"schema_version": 1,
            "run_id": request["run_id"], "reservation_id": request["reservation_id"],
            "stage_id": request["stage_id"], "index": index, "event": event}), max_bytes=4096)
        attempts[event["attempt_id"]] = (route, phase)
        index += 1
    profile = request["profile"]
    wrapped = OneGenerationTransport(transport_factory(policy, observer=observe), store,
        reservation_id=request["reservation_id"], stage_id=request["stage_id"], origin=policy.origin,
        model=profile["selectors"][0], max_tokens=request["max_tokens"])
    if request["stage_id"] == "readiness":
        call = lambda: probe_profile(profile, prompt=request["messages"][0]["content"],
            timeout_seconds=request["timeout_seconds"], max_tokens=32, seed=request["seed"],
            run_id=request["run_id"], transport=wrapped)
    else:
        backend = OllamaBackend(base_url=policy.origin, model=profile["selectors"][0], transport=wrapped,
            timeout=request["timeout_seconds"], num_ctx=profile["generation_config"]["num_ctx"])
        call = lambda: backend.chat(request["messages"], system=request["system"],
            max_tokens=request["max_tokens"], temperature=request["temperature"], seed=request["seed"])
    result = execute_backend_once(wrapped, call)
    store.put("worker-result.json", canonical_bytes({"schema_version": 1,
        "request_sha256": hashlib.sha256(canonical_bytes(request)).hexdigest(),
        "reservation_id": request["reservation_id"], "result": result}), max_bytes=2097152)
    return result


def _unknown(code):
    return {"outcome": "unknown", "backend_valid": False, "text": None, "failure": code, "backend_result": None}


def supervise_generation(request, *, exchange, reservation, ledger, repository, python_executable,
                         timeout_seconds, launcher=start_owned_process):
    """Require the parent's durable budget proof before any owned child resumes."""
    started, owned = time.monotonic(), None
    try:
        _require(type(reservation) is dict and set(reservation) == {"record_name", "sha256"})
        _require(type(reservation["record_name"]) is str and bool(re.fullmatch(r"ledger-[0-9]{4}\.json", reservation["record_name"]))
                 and type(reservation["sha256"]) is str and bool(re.fullmatch(r"[0-9a-f]{64}", reservation["sha256"])))
        proof = strict_load_json(ledger.read(reservation["record_name"], max_bytes=8192,
            expected_sha256=reservation["sha256"]), max_bytes=8192)
        _validate(request, proof)
        _require(_seconds(timeout_seconds, 240) and repository.is_absolute() and python_executable.is_absolute()
                 and (repository / "harness" / "bulletin_model_worker.py").is_file() and python_executable.is_file())
        descriptor = {"schema_version": 1, "request": request,
            "request_sha256": hashlib.sha256(canonical_bytes(request)).hexdigest(),
            "exchange_path": str(exchange.path), "exchange_identity": exchange.identity.to_json_dict(),
            "reservation_record": proof}
        stdin = canonical_bytes(descriptor)
        _require(len(stdin) <= 147456)
        # Created-only launch marker prevents another supervisor from replaying this exchange.
        exchange.put("worker-launch.json", stdin, max_bytes=147456)
        claim = hashlib.sha256(request["reservation_id"].encode("ascii")).hexdigest()[:32]
        ledger.put(f"worker-claim-{claim}.json", canonical_bytes({"schema_version": 1,
            "reservation_id": request["reservation_id"], "request_sha256": descriptor["request_sha256"],
            "exchange_identity": descriptor["exchange_identity"]}), max_bytes=8192)
        bootstrap = "import sys;sys.path.insert(0,sys.argv[1]);from harness.bulletin_model_worker import main;raise SystemExit(main())"
        env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
        owned = launcher((str(python_executable), "-I", "-S", "-c", bootstrap, str(repository)),
            cwd=repository, stdin_bytes=stdin, env=env)
        remaining = timeout_seconds - (time.monotonic() - started)
        if remaining <= 0 or not owned.resume():
            owned.signal_tree()
            return _unknown("worker_not_resumed")
        outcome = owned.wait(remaining)
        timed_out = outcome is None
        if timed_out:
            owned.signal_tree()
            outcome = owned.wait(.5)
            if outcome is None:
                return _unknown("worker_timeout")
        for name, value in (("worker-stdout.txt", outcome.stdout), ("worker-stderr.txt", outcome.stderr)):
            exchange.put(name, value.encode("utf-8", "strict"), max_bytes=1048576)
        exchange.put("worker-process.json", canonical_bytes({"schema_version": 1,
            "reservation_id": request["reservation_id"], "timed_out": timed_out,
            "returncode": outcome.returncode, "elapsed_ms": outcome.elapsed_ms,
            "malformed_output": outcome.malformed_output}), max_bytes=8192)
        if timed_out:
            return _unknown("worker_timeout")
        if outcome.returncode != 0 or outcome.malformed_output or outcome.timed_out:
            return _unknown("worker_process_incomplete")
        saved = strict_load_json(exchange.read("worker-result.json", max_bytes=2097152),
                                 max_bytes=2097152, max_depth=24)
        _require(type(saved) is dict and set(saved) == {"schema_version", "request_sha256", "reservation_id", "result"}
                 and type(saved["schema_version"]) is int and saved["schema_version"] == 1
                 and saved["request_sha256"] == descriptor["request_sha256"]
                 and saved["reservation_id"] == request["reservation_id"] and type(saved["result"]) is dict)
        result = saved["result"]
        _require(set(result) == {"outcome", "backend_valid", "text", "failure", "backend_result"}
                 and result["outcome"] in ("response_received", "no_send", "unknown")
                 and type(result["backend_valid"]) is bool
                 and (result["text"] is None or type(result["text"]) is str)
                 and (result["failure"] is None or result["failure"] in {
                    "BackendError", "MalformedBackendOutput", "CallError", "backend_call_failed",
                    "transport_or_capture_incomplete", "generation_response_missing", "invalid_assistant_text",
                    "backend_result_missing", "backend_result_rejected", "readiness_rejected", "capture_recheck_failed"})
                 and (result["backend_result"] is None or type(result["backend_result"]) is dict))
        _require(not result["backend_valid"] or (result["outcome"] == "response_received"
                 and type(result["text"]) is str and result["failure"] is None))
        return result
    except Exception as exc:
        if owned is not None:
            owned.signal_tree()
            return _unknown("worker_supervision_incomplete")
        raise WorkerError("worker_not_launched") from exc
    finally:
        if owned is not None:
            owned.close()


def main():
    try:
        raw = sys.stdin.buffer.read(147457)
        value = strict_load_json(raw, max_bytes=147456, max_depth=24)
        _require(type(value) is dict and set(value) == {"schema_version", "request", "request_sha256",
            "exchange_path", "exchange_identity", "reservation_record"} and type(value["schema_version"]) is int
            and value["schema_version"] == 1 and hashlib.sha256(canonical_bytes(value["request"])).hexdigest() == value["request_sha256"])
        identity = value["exchange_identity"]
        _require(type(identity) is dict and set(identity) == {"platform", "device", "inode"})
        with PrivateExchange.attach(Path(value["exchange_path"]),
                expected=ArtifactIdentity.from_json_dict(identity)) as exchange:
            _require(exchange.read("worker-launch.json", max_bytes=147456) == raw)
            exchange.put("worker-started.json", canonical_bytes({"schema_version": 1,
                "request_sha256": value["request_sha256"]}), max_bytes=8192)
            run_worker(value["request"], exchange, value["reservation_record"])
        return 0
    except Exception:
        sys.stderr.write("BULLETIN_MODEL_WORKER_INCOMPLETE\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
