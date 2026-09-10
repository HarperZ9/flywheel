"""Disk accounting controls use scripted transport only, never model endpoints."""
from contextlib import contextmanager, ExitStack
import json
from pathlib import Path
import sys

import pytest

from harness.bulletin_model_budget import CampaignBudget
from harness.bulletin_model_exchange import PrivateExchange
from harness.bulletin_model_reconcile import reconcile_generation_accounting
from harness.bulletin_model_worker import run_worker, supervise_generation
from harness.cross_harness_process import ProcessOutcome
from harness.evidence_json import canonical_bytes
from tests.test_bulletin_model_worker import request, fixture_factory


@contextmanager
def campaign(tmp_path, *, digest="a" * 64, usage=None, extra=None, model="fixture", text="received"):
    with PrivateExchange.create(tmp_path / "ledger") as ledger, PrivateExchange.create(tmp_path / "readiness") as call, ExitStack() as stack:
        refs, original = [], ledger.put
        def record(name, raw, **kw):
            sha = original(name, raw, **kw)
            if name.startswith("ledger-"):
                refs.append({"record_name": name, "sha256": sha})
            return sha
        ledger.put = record
        budget = CampaignBudget(ledger, "run")
        req = request()
        rid = budget.reserve("readiness", 32)
        def factory(policy, *, observer):
            def event(row):
                if req["stage_id"] == "smoke":
                    row = {**row, "attempt_id": "bbbbbbbb" + row["attempt_id"][8:]}
                observer(row)
            transport = fixture_factory([], digest=digest, model=model, text=text)(policy, observer=event)
            def send(*args):
                status, response = transport(*args)
                if args[0] == "POST" and usage is not None:
                    response.update(usage)
                return status, response
            return send
        def launch(argv, **kw):
            descriptor = json.loads(kw["stdin_bytes"])
            class Owned:
                def resume(self):
                    call.put("worker-started.json", canonical_bytes({"schema_version": 1,
                        "request_sha256": descriptor["request_sha256"]}), max_bytes=8192)
                    run_worker(req, call, descriptor["reservation_record"], transport_factory=factory)
                    return True
                def wait(self, timeout): return ProcessOutcome(0, "", "", 20, False)
                def signal_tree(self): return True
                def close(self): pass
            return Owned()
        result = supervise_generation(req, exchange=call, reservation=budget.reservation_evidence(rid),
            ledger=ledger, repository=Path.cwd(), python_executable=Path(sys.executable),
            timeout_seconds=2, launcher=launch)
        budget.finish(rid, result["outcome"])
        if extra is not None:
            first, call = call, stack.enter_context(PrivateExchange.create(tmp_path / "smoke"))
            req, usage = request("smoke"), {"eval_count": 2}
            req["system"] = "Keep the report scoped."
            rid = budget.reserve("smoke", 256)
            result = supervise_generation(req, exchange=call, reservation=budget.reservation_evidence(rid),
                ledger=ledger, repository=Path.cwd(), python_executable=Path(sys.executable),
                timeout_seconds=2, launcher=launch)
            budget.finish(rid, result["outcome"])
            extra["smoke"], call = call, first
        yield ledger, call, refs


def reconcile(ledger, call, refs):
    return reconcile_generation_accounting(run_id="run", ledger=ledger, ledger_refs=refs,
        invocations={"readiness": call})


def test_separate_plan_reservation_start_health_post_capture_and_nullable_usage(tmp_path):
    with campaign(tmp_path) as (ledger, call, refs):
        report = reconcile(ledger, call, refs)
        assert report["reconciled"] is True
        assert report["planned_generations"] == 38 and report["reserved_generations"] == 1
        assert report["requested_output_tokens"] == 32 and report["worker_starts_observed"] == 1
        assert report["response_captures"] == 1
        assert report["transport"]["health"]["attempts_observed"] == 1
        assert report["transport"]["generation"]["attempts_observed"] == 1
        assert report["native_usage"]["eval_count"]["total"] == 3
        assert report["native_usage"]["prompt_eval_count"]["total"] is None
        assert report["delivery_count"] is None


@pytest.mark.parametrize("name", ["worker-started.json", "transport-001.json", "response.json", "worker-result.json"])
def test_missing_required_receipt_fails_prefix_without_fabricating_zero(tmp_path, name):
    with campaign(tmp_path) as (ledger, call, refs):
        (call.path / name).unlink()
        report = reconcile(ledger, call, refs)
        assert report["reconciled"] is False and report["gaps"]
        assert report["native_usage"]["eval_count"]["total"] is None


def test_bool_usage_is_unknown_not_one(tmp_path):
    with campaign(tmp_path, usage={"eval_count": True}) as (ledger, call, refs):
        report = reconcile(ledger, call, refs)
        assert report["native_usage"]["eval_count"]["total"] is None


def test_health_rejection_proves_zero_generating_requests(tmp_path):
    with campaign(tmp_path, digest="b" * 64) as (ledger, call, refs):
        report = reconcile(ledger, call, refs)
        assert report["reconciled"] is True
        assert report["transport"]["health"]["attempts_observed"] == 1
        assert report["transport"]["generation"]["attempts_observed"] == 0
        assert report["native_usage"]["eval_count"]["total"] == 0


@pytest.mark.parametrize("case", ["ledger_hash", "forged_terminal", "wrong_binding", "repeated_attempt"])
def test_tampered_receipts_never_reconcile(tmp_path, case):
    with campaign(tmp_path) as (ledger, call, refs):
        if case == "ledger_hash":
            refs[-1]["sha256"] = "0" * 64
        else:
            name = "transport-005.json"
            row = json.loads((call.path / name).read_bytes())
            if case == "forged_terminal": row["event"]["request_send_started"] = False
            elif case == "wrong_binding": row["reservation_id"] = "other"
            else: row["event"]["attempt_id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
            (call.path / name).write_bytes(canonical_bytes(row))
        report = reconcile(ledger, call, refs)
        assert report["reconciled"] is False
        if case == "ledger_hash":
            assert report["reserved_generations"] is None and report["requested_output_tokens"] is None
            assert report["unknown_generation_terminals"] is None
            assert report["validated_ledger_prefix"]["reservations"] == 1


def test_pending_reservation_is_unknown_not_completed_generation(tmp_path):
    with PrivateExchange.create(tmp_path / "ledger") as ledger:
        refs, original = [], ledger.put
        def record(name, raw, **kw):
            sha = original(name, raw, **kw)
            refs.append({"record_name": name, "sha256": sha})
            return sha
        ledger.put = record
        budget = CampaignBudget(ledger, "run")
        budget.reserve("readiness", 32)
        report = reconcile_generation_accounting(run_id="run", ledger=ledger, ledger_refs=refs, invocations={})
        assert report["reconciled"] is False and report["missing_generation_terminals"] == 1
        assert report["worker_starts_observed"] == 0 and report["response_captures"] == 0
        assert report["native_usage"]["eval_count"]["total"] is None


def test_unknown_terminal_is_preserved_even_with_received_response(tmp_path):
    import hashlib
    with campaign(tmp_path) as (ledger, call, refs):
        path = ledger.path / refs[-1]["record_name"]
        row = json.loads(path.read_bytes())
        row["outcome"] = "unknown"
        raw = canonical_bytes(row)
        path.write_bytes(raw)
        refs[-1]["sha256"] = hashlib.sha256(raw).hexdigest()
        report = reconcile(ledger, call, refs)
        assert not report["reconciled"] and report["unknown_generation_terminals"] == 1
        assert report["response_captures"] == 1
        assert report["invocations"][0]["terminal"] == "unknown"
        assert report["native_usage"]["eval_count"]["total"] is None


def test_response_terminal_without_durable_send_intent_is_not_reconciled(tmp_path):
    with campaign(tmp_path) as (ledger, call, refs):
        terminal = (call.path / "transport-005.json").read_bytes()
        row = json.loads(terminal)
        row["index"] = 4
        (call.path / "transport-004.json").write_bytes(canonical_bytes(row))
        (call.path / "transport-005.json").unlink()
        report = reconcile(ledger, call, refs)
        assert report["reconciled"] is False


def test_field_aggregate_requires_every_used_invocation_field(tmp_path):
    extra = {}
    with campaign(tmp_path, usage={"eval_count": 0, "prompt_eval_count": 7}, extra=extra) as (ledger, call, refs):
        report = reconcile_generation_accounting(run_id="run", ledger=ledger, ledger_refs=refs,
            invocations={"readiness": call, **extra})
        assert report["reconciled"] and report["response_captures"] == 2
        assert report["requested_output_tokens"] == 288
        assert report["native_usage"]["eval_count"]["total"] == 2
        assert report["native_usage"]["prompt_eval_count"]["total"] is None
        assert report["native_usage"]["prompt_eval_count"]["covered_invocations"] == 1
        assert report["native_usage"]["prompt_eval_count"]["required_invocations"] == 2
        assert report["native_usage"]["total_duration"]["total"] is None


def test_repeated_transport_uuid_across_stages_fails_reconciliation(tmp_path):
    extra = {}
    with campaign(tmp_path, extra=extra) as (ledger, call, refs):
        for index in range(3):
            path = extra["smoke"].path / f"transport-{index:03d}.json"
            row = json.loads(path.read_bytes())
            row["event"]["attempt_id"] = "aaaaaaaa" + row["event"]["attempt_id"][8:]
            path.write_bytes(canonical_bytes(row))
        report = reconcile_generation_accounting(run_id="run", ledger=ledger, ledger_refs=refs,
            invocations={"readiness": call, **extra})
        assert report["reconciled"] is False
        assert report["native_usage"]["eval_count"]["total"] is None


@pytest.mark.parametrize("stage", ["readiness", "smoke"])
@pytest.mark.parametrize("case", ["messages", "system", "num_ctx", "seed", "temperature", "extra_option", "stream"])
def test_entire_generation_request_is_bound_to_admitted_worker_request(tmp_path, stage, case):
    extra = {} if stage == "smoke" else None
    with campaign(tmp_path, extra=extra) as (ledger, call, refs):
        stores = {"readiness": call, **(extra or {})}
        path = stores[stage].path / "request.bin"
        body = json.loads(path.read_bytes())
        if case == "messages": body["messages"] = [{"role": "user", "content": "changed"}]
        elif case == "system": body["messages"][0]["content"] = "different system instruction"
        elif case == "stream": body["stream"] = True
        else: body["options"][case] = {"num_ctx": 2048, "seed": 5, "temperature": 1.0, "extra_option": 7}[case]
        path.write_bytes(canonical_bytes(body))
        report = reconcile_generation_accounting(run_id="run", ledger=ledger, ledger_refs=refs, invocations=stores)
        assert not report["reconciled"] and report["gaps"]


@pytest.mark.parametrize("case", ["worker_text", "assistant_text", "text_state"])
def test_returned_text_and_text_artifact_match_capture_exactly(tmp_path, case):
    with campaign(tmp_path, text="original é\n") as (ledger, call, refs):
        if case == "assistant_text":
            (call.path / "assistant.txt").write_bytes(b"changed")
        else:
            name = "worker-result.json" if case == "worker_text" else "response.json"
            path = call.path / name
            row = json.loads(path.read_bytes())
            if case == "worker_text": row["result"]["text"] = "changed"
            else: row["assistant_text_state"] = "invalid_or_missing"
            path.write_bytes(canonical_bytes(row))
        report = reconcile(ledger, call, refs)
        assert not report["reconciled"] and report["native_usage"]["eval_count"]["total"] is None


@pytest.mark.parametrize("model,text", [("other", "rejected identity"), (None, "missing identity"), ("fixture", 17)])
def test_rejected_response_still_reconciles_capture_and_usage(tmp_path, model, text):
    with campaign(tmp_path, model=model, text=text) as (ledger, call, refs):
        saved = json.loads((call.path / "worker-result.json").read_bytes())
        assert saved["result"]["backend_valid"] is False
        report = reconcile(ledger, call, refs)
        assert report["reconciled"] and report["response_captures"] == 1
        assert report["native_usage"]["eval_count"]["total"] == 3


@pytest.mark.parametrize("field,value", [("text", "changed backend text"), ("generation_config", {})])
def test_backend_result_cannot_disagree_with_bound_request_and_capture(tmp_path, field, value):
    extra = {}
    with campaign(tmp_path, extra=extra) as (ledger, call, refs):
        path = extra["smoke"].path / "worker-result.json"
        row = json.loads(path.read_bytes())
        row["result"]["backend_result"][field] = value
        path.write_bytes(canonical_bytes(row))
        report = reconcile_generation_accounting(run_id="run", ledger=ledger, ledger_refs=refs,
            invocations={"readiness": call, **extra})
        assert not report["reconciled"] and report["gaps"]
