"""Stateful UnisonAI-inspired benchmark fixtures.

This module treats UnisonAI as benchmark pressure, not as verified upstream
performance evidence. The fixture checks concrete local-engine behaviors:
correction replay after restart, anti-ledger withholding, fixed scorecard
receipts, and Discord channel scope locking.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any


SCHEMA = "unisonai.stateful-benchmark/v1"


def _hash(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _metric(name: str, value: float | int | bool | str) -> dict[str, Any]:
    return {"metric": name, "value": value}


class FixtureEngine:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "state.json"
        self.state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "memory": {},
                "anti_ledger": {},
                "territories": {},
                "scorecards": [],
                "discord_events": [],
                "events": [],
            }
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def _event(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "kind": kind,
            "payload": payload,
            "event_sha256": _hash({"kind": kind, "payload": payload}),
        }
        self.state["events"].append(event)
        return event

    def correct(self, question: str, bad_answer: str, good_answer: str, territory: str) -> None:
        self.state["anti_ledger"][question] = {
            "rejected_answer_sha256": _hash(bad_answer),
            "reason": "explicit correction fixture",
        }
        self.state["memory"][question] = {
            "answer": good_answer,
            "territory": territory,
            "source": "human_correction_fixture",
        }
        territory_state = self.state["territories"].setdefault(
            territory,
            {"corrections": 0, "teacher_retired": False},
        )
        territory_state["corrections"] += 1
        if territory_state["corrections"] >= 2:
            territory_state["teacher_retired"] = True
        self._event("correction", {
            "question_sha256": _hash(question),
            "good_answer_sha256": _hash(good_answer),
            "territory": territory,
        })
        self.save()

    def answer(self, question: str) -> dict[str, Any]:
        memory = self.state["memory"].get(question)
        anti = self.state["anti_ledger"].get(question)
        if memory:
            response = {
                "answer": memory["answer"],
                "source": memory["source"],
                "withheld_rejected_answer": bool(anti),
            }
        else:
            response = {
                "answer": "UNVERIFIABLE",
                "source": "no_persistent_memory",
                "withheld_rejected_answer": bool(anti),
            }
        self._event("answer", {
            "question_sha256": _hash(question),
            "response_sha256": _hash(response),
        })
        self.save()
        return response

    def self_play_probe(self, question: str, proposed_answer: str) -> dict[str, Any]:
        before = _hash(self.state["memory"])
        verdict = "reject_unverified"
        if question in self.state["memory"]:
            verdict = "held_memory"
        after = _hash(self.state["memory"])
        result = {
            "question_sha256": _hash(question),
            "proposed_answer_sha256": _hash(proposed_answer),
            "verdict": verdict,
            "memory_unchanged": before == after,
        }
        self._event("self_play_probe", result)
        self.save()
        return result

    def scorecard(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        scored = []
        for item in items:
            scored.append({
                "item_id": item["id"],
                "model_ref": item["model_ref"],
                "answer_sha256": _hash(item["answer"]),
                "expected_sha256": _hash(item["expected"]),
                "correct": item["answer"] == item["expected"],
            })
        receipt = {
            "items": scored,
            "score": round(sum(1 for item in scored if item["correct"]) / len(scored), 3),
            "receipt_sha256": _hash(scored),
        }
        self.state["scorecards"].append(receipt)
        self._event("scorecard", {"receipt_sha256": receipt["receipt_sha256"]})
        self.save()
        return receipt

    def discord_ingest(
        self,
        *,
        configured_channel: str,
        channel_id: str,
        text: str,
        token: str,
        tool_trace: dict[str, Any],
    ) -> dict[str, Any]:
        accepted = channel_id == configured_channel and token not in text
        event = {
            "channel_id": channel_id,
            "accepted": accepted,
            "reason": "accepted" if accepted else "scope_or_secret_boundary",
            "text_sha256": _hash(text),
            "tool_trace_sha256": _hash(tool_trace),
        }
        self.state["discord_events"].append(event)
        self._event("discord_ingest", event)
        self.save()
        return event


def run_unisonai_stateful_benchmark(state_root: Path) -> dict[str, Any]:
    engine = FixtureEngine(state_root)
    question = "What is 2 + 2?"
    engine.correct(question, "5", "4", "arithmetic")
    engine.correct("What is 3 + 3?", "7", "6", "arithmetic")

    restarted = FixtureEngine(state_root)
    replay = restarted.answer(question)
    self_play = restarted.self_play_probe("What is the capital of Atlantis?", "Poseidon City")
    scorecard_a = restarted.scorecard([
        {"id": "fixed-001", "model_ref": "fixture/local-engine", "answer": "4", "expected": "4"},
        {"id": "fixed-002", "model_ref": "fixture/local-engine", "answer": "blue", "expected": "red"},
    ])
    scorecard_b = restarted.scorecard([
        {"id": "fixed-001", "model_ref": "fixture/local-engine", "answer": "4", "expected": "4"},
        {"id": "fixed-002", "model_ref": "fixture/local-engine", "answer": "blue", "expected": "red"},
    ])
    accepted = restarted.discord_ingest(
        configured_channel="channel-allowed",
        channel_id="channel-allowed",
        text="Document received; tool trace attached.",
        token="bot-secret",
        tool_trace={"tool": "ingest", "status": "ok", "document_sha256": _hash("doc")},
    )
    rejected = restarted.discord_ingest(
        configured_channel="channel-allowed",
        channel_id="channel-other",
        text="bot-secret leaked",
        token="bot-secret",
        tool_trace={"tool": "ingest", "status": "blocked"},
    )

    territories = restarted.state["territories"]
    checks = {
        "correction_permanence_score": replay["answer"] == "4",
        "negative_ledger_enforcement": replay["withheld_rejected_answer"],
        "persistent_memory_replay_score": replay["source"] == "human_correction_fixture",
        "teacher_exit_evidence_score": territories["arithmetic"]["teacher_retired"],
        "selfplay_nonreinforcement_score": self_play["memory_unchanged"],
        "fixed_item_scorecard_reproducibility": (
            scorecard_a["receipt_sha256"] == scorecard_b["receipt_sha256"]
        ),
        "negative_result_preservation": scorecard_a["score"] < 1.0,
        "discord_scope_lock_score": accepted["accepted"] and not rejected["accepted"],
        "tool_trace_receipt_completeness": bool(accepted["tool_trace_sha256"]),
        "secret_boundary_score": "bot-secret" not in json.dumps(restarted.state),
    }
    metrics = [_metric(name, 1.0 if passed else 0.0) for name, passed in checks.items()]
    pass_rate = round(mean(float(metric["value"]) for metric in metrics), 3)
    result = {
        "schema": SCHEMA,
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "state_root": str(state_root),
        "source": "https://github.com/MettaMazza/UnisonAI",
        "source_boundary": "public README claims converted into local deterministic fixtures",
        "passed": pass_rate == 1.0,
        "pass_rate": pass_rate,
        "metrics": metrics,
        "receipts": {
            "state_sha256": _hash(restarted.state),
            "event_count": len(restarted.state["events"]),
            "scorecard_receipt_sha256": scorecard_a["receipt_sha256"],
            "discord_accept_receipt_sha256": accepted["tool_trace_sha256"],
            "discord_reject_receipt_sha256": rejected["tool_trace_sha256"],
        },
        "checks": checks,
    }
    result["packet_sha256"] = _hash(result)
    return result


def _render_provider_matrix_markdown(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    lines = [
        "# UnisonAI Stateful Provider Matrix",
        "",
        f"- schema: `{result.get('schema', '')}`",
        f"- providers_requested: `{', '.join(result.get('providers_requested', []))}`",
        f"- provider_roles_requested: `{', '.join(result.get('provider_roles_requested', []))}`",
        f"- rows: `{summary.get('rows', 0)}`",
        f"- operational_rows: `{summary.get('operational_rows', 0)}`",
        f"- failed_rows: `{summary.get('failed_rows', 0)}`",
        f"- mean_pass_rate: `{summary.get('mean_pass_rate', 0.0)}`",
        f"- repair_success_rate: `{summary.get('repair_success_rate', 0.0)}`",
        "",
        "## Rows",
        "",
        "| Provider | Role | Live | Operational | Passed | Pass rate | Failure | Actions |",
        "|---|---|---:|---:|---:|---:|---|---:|",
    ]
    for row in result.get("rows", []):
        lines.append(
            "| {provider} | {role} | {live} | {operational} | {passed} | {pass_rate} | {failure} | {actions} |".format(
                provider=row.get("provider", ""),
                role=row.get("provider_role", ""),
                live=str(row.get("live", False)).lower(),
                operational=str(row.get("operational", False)).lower(),
                passed=str(row.get("passed", False)).lower(),
                pass_rate=row.get("pass_rate", 0.0),
                failure=row.get("failure_class", ""),
                actions=row.get("action_count", 0),
            )
        )
    return "\n".join(lines) + "\n"


def render_markdown(result: dict[str, Any]) -> str:
    if result.get("schema") == "unisonai.stateful-provider-matrix/v1":
        return _render_provider_matrix_markdown(result)

    lines = [
        "# UnisonAI Stateful Benchmark",
        "",
        f"- schema: `{result['schema']}`",
        f"- state_root: `{result['state_root']}`",
        f"- passed: `{result['passed']}`",
        f"- pass_rate: `{result['pass_rate']}`",
        f"- packet_sha256: `{result['packet_sha256']}`",
        "",
        "## Metrics",
        "",
    ]
    lines.extend(f"- `{item['metric']}`: `{item['value']}`" for item in result["metrics"])
    lines.extend(["", "## Receipts", ""])
    lines.extend(f"- `{key}`: `{value}`" for key, value in result["receipts"].items())
    return "\n".join(lines) + "\n"


def _extract_actions(text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("malformed_action_json") from None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            raise ValueError("malformed_action_json") from None
    actions = payload.get("actions") if isinstance(payload, dict) else payload
    if not isinstance(actions, list):
        raise ValueError("malformed_action_json")
    if not actions:
        raise ValueError("malformed_action_json")
    if not all(isinstance(action, dict) and action.get("op") for action in actions):
        raise ValueError("malformed_action_json")
    return actions


def _apply_action(engine: FixtureEngine, action: dict[str, Any]) -> Any:
    op = str(action.get("op", ""))
    if op == "correct":
        engine.correct(
            str(action["question"]),
            str(action["bad_answer"]),
            str(action["good_answer"]),
            str(action["territory"]),
        )
        return {"op": op, "status": "ok"}
    if op == "answer":
        return engine.answer(str(action["question"]))
    if op == "self_play_probe":
        return engine.self_play_probe(
            str(action["question"]),
            str(action["proposed_answer"]),
        )
    if op == "scorecard":
        items = action.get("items")
        if not isinstance(items, list):
            raise ValueError("scorecard items must be a list")
        return engine.scorecard(items)
    if op == "discord_ingest":
        return engine.discord_ingest(
            configured_channel=str(action["configured_channel"]),
            channel_id=str(action["channel_id"]),
            text=str(action["text"]),
            token=str(action["token"]),
            tool_trace=dict(action.get("tool_trace", {})),
        )
    raise ValueError(f"unsupported action op: {op}")


def _backend_action_prompt() -> str:
    return (
        "Return JSON only with an `actions` array. Required operations: two "
        "correct actions in the same territory, answer replay for the first "
        "question, self_play_probe for an unknown claim, two identical scorecard "
        "actions with one negative result preserved, one accepted discord_ingest "
        "inside configured channel, and one rejected discord_ingest outside scope "
        "or with secret text. Do not return prose."
    )


def _repair_prompt(raw_text: str) -> str:
    return (
        "Repair the previous response into JSON only. Return an object with an "
        "`actions` array. Do not explain. Previous response SHA256: "
        f"{_hash(raw_text)}"
    )


def _stateful_backend_failure(
    *,
    backend_name: str,
    model_ref: str,
    state_root: Path,
    failure_class: str,
    error: str,
    repair: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "schema": "unisonai.stateful-backend-benchmark/v1",
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "backend_name": backend_name,
        "model_ref": model_ref,
        "state_root": str(state_root),
        "passed": False,
        "pass_rate": 0.0,
        "failure_class": failure_class,
        "error": error,
        "action_count": 0,
        "metrics": [_metric("provider_action_execution_score", 0.0)],
        "receipts": {},
    }
    if repair is not None:
        result["repair"] = repair
    result["packet_sha256"] = _hash(result)
    return result


def run_unisonai_stateful_backend_benchmark(
    backend: Any,
    state_root: Path,
    *,
    seed: int = 0,
    max_tokens: int = 1200,
    repair_json: bool = False,
) -> dict[str, Any]:
    """Ask a backend for structured actions and execute them against the fixture.

    This is deliberately stricter than the source-mined prompt benchmark. Prose
    is not credited. The backend must emit JSON actions; the benchmark scores the
    resulting local state and receipts.
    """
    backend_name = str(getattr(backend, "name", "unknown-backend"))
    try:
        raw = backend.chat(
            [{"role": "user", "content": _backend_action_prompt()}],
            system="unisonai stateful fixture action benchmark",
            max_tokens=max_tokens,
            temperature=0.0,
            seed=seed,
        )
    except Exception as exc:  # noqa: BLE001 - benchmark records provider failure.
        return _stateful_backend_failure(
            backend_name=backend_name,
            model_ref=backend_name,
            state_root=state_root,
            failure_class="provider_error",
            error=str(exc),
        )
    text = str(raw.get("text", ""))
    model_ref = str(raw.get("model_ref", backend_name))
    repair = {
        "attempted": False,
        "succeeded": False,
        "raw_response_sha256": _hash(text),
        "repair_response_sha256": "",
    }
    try:
        actions = _extract_actions(text)
    except ValueError as exc:
        if repair_json:
            repair["attempted"] = True
            try:
                repaired_raw = backend.chat(
                    [{"role": "user", "content": _repair_prompt(text)}],
                    system="unisonai stateful fixture JSON repair",
                    max_tokens=max_tokens,
                    temperature=0.0,
                    seed=seed + 1,
                )
            except Exception as repair_exc:  # noqa: BLE001 - benchmark records provider failure.
                repair["error"] = str(repair_exc)
                return _stateful_backend_failure(
                    backend_name=backend_name,
                    model_ref=model_ref,
                    state_root=state_root,
                    failure_class="repair_provider_error",
                    error=str(repair_exc),
                    repair=repair,
                )
            repaired_text = str(repaired_raw.get("text", ""))
            repair["repair_response_sha256"] = _hash(repaired_text)
            try:
                actions = _extract_actions(repaired_text)
            except ValueError:
                return _stateful_backend_failure(
                    backend_name=backend_name,
                    model_ref=model_ref,
                    state_root=state_root,
                    failure_class="malformed_action_json",
                    error=str(exc),
                    repair=repair,
                )
            repair["succeeded"] = True
        else:
            return _stateful_backend_failure(
                backend_name=backend_name,
                model_ref=model_ref,
                state_root=state_root,
                failure_class="malformed_action_json",
                error=str(exc),
                repair=repair,
            )

    engine = FixtureEngine(state_root)
    action_results = []
    try:
        for action in actions:
            action_results.append(_apply_action(engine, action))
    except (KeyError, TypeError, ValueError) as exc:
        return _stateful_backend_failure(
            backend_name=backend_name,
            model_ref=model_ref,
            state_root=state_root,
            failure_class="invalid_action",
            error=str(exc),
            repair=repair,
        )

    restarted = FixtureEngine(state_root)
    replay = restarted.answer("What is 2 + 2?")
    scorecards = restarted.state.get("scorecards", [])
    discord_events = restarted.state.get("discord_events", [])
    self_play_events = [
        event.get("payload", {})
        for event in restarted.state.get("events", [])
        if event.get("kind") == "self_play_probe"
    ]
    territories = restarted.state.get("territories", {})
    checks = {
        "provider_action_execution_score": len(action_results) == len(actions),
        "correction_permanence_score": replay.get("answer") == "4",
        "negative_ledger_enforcement": bool(replay.get("withheld_rejected_answer")),
        "persistent_memory_replay_score": replay.get("source") == "human_correction_fixture",
        "teacher_exit_evidence_score": bool(
            territories.get("arithmetic", {}).get("teacher_retired")
        ),
        "selfplay_nonreinforcement_score": any(
            item.get("memory_unchanged") for item in self_play_events
        ),
        "fixed_item_scorecard_reproducibility": (
            len(scorecards) >= 2
            and scorecards[-1].get("receipt_sha256") == scorecards[-2].get("receipt_sha256")
        ),
        "negative_result_preservation": bool(scorecards and scorecards[-1].get("score", 1.0) < 1.0),
        "discord_scope_lock_score": (
            any(item.get("accepted") for item in discord_events)
            and any(not item.get("accepted") for item in discord_events)
        ),
        "tool_trace_receipt_completeness": all(
            item.get("tool_trace_sha256") for item in discord_events
        ),
        "secret_boundary_score": "bot-secret" not in json.dumps(restarted.state),
    }
    metrics = [_metric(name, 1.0 if passed else 0.0) for name, passed in checks.items()]
    pass_rate = round(mean(float(metric["value"]) for metric in metrics), 3)
    result = {
        "schema": "unisonai.stateful-backend-benchmark/v1",
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "backend_name": backend_name,
        "model_ref": model_ref,
        "state_root": str(state_root),
        "passed": pass_rate == 1.0,
        "pass_rate": pass_rate,
        "failure_class": "none" if pass_rate == 1.0 else "stateful_fixture_miss",
        "error": "",
        "action_count": len(actions),
        "metrics": metrics,
        "receipts": {
            "state_sha256": _hash(restarted.state),
            "event_count": len(restarted.state["events"]),
            "scorecard_receipt_sha256": scorecards[-1].get("receipt_sha256", "")
            if scorecards
            else "",
        },
        "checks": checks,
        "repair": repair,
    }
    result["packet_sha256"] = _hash(result)
    return result
