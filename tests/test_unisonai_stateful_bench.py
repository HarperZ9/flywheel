import json

from scripts.run_unisonai_stateful_benchmark import main
from harness.unisonai_stateful_bench import run_unisonai_stateful_backend_benchmark


class ScriptedBackend:
    name = "scripted-unison"

    def __init__(self, text):
        self.text = text

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": self.text, "model_ref": "scripted:model", "seed": seed}


class SequenceBackend:
    name = "sequence-unison"

    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        text = self.texts[min(self.calls, len(self.texts) - 1)]
        self.calls += 1
        return {"text": text, "model_ref": "sequence:model", "seed": seed}


def _actions_json():
    return json.dumps({
        "actions": [
            {
                "op": "correct",
                "question": "What is 2 + 2?",
                "bad_answer": "5",
                "good_answer": "4",
                "territory": "arithmetic",
            },
            {
                "op": "correct",
                "question": "What is 3 + 3?",
                "bad_answer": "7",
                "good_answer": "6",
                "territory": "arithmetic",
            },
            {"op": "answer", "question": "What is 2 + 2?"},
            {
                "op": "self_play_probe",
                "question": "What is the capital of Atlantis?",
                "proposed_answer": "Poseidon City",
            },
            {
                "op": "scorecard",
                "items": [
                    {"id": "fixed-001", "model_ref": "sequence:model", "answer": "4", "expected": "4"},
                    {"id": "fixed-002", "model_ref": "sequence:model", "answer": "blue", "expected": "red"},
                ],
            },
            {
                "op": "scorecard",
                "items": [
                    {"id": "fixed-001", "model_ref": "sequence:model", "answer": "4", "expected": "4"},
                    {"id": "fixed-002", "model_ref": "sequence:model", "answer": "blue", "expected": "red"},
                ],
            },
            {
                "op": "discord_ingest",
                "configured_channel": "channel-allowed",
                "channel_id": "channel-allowed",
                "text": "Document received; tool trace attached.",
                "token": "bot-secret",
                "tool_trace": {"tool": "ingest", "status": "ok"},
            },
            {
                "op": "discord_ingest",
                "configured_channel": "channel-allowed",
                "channel_id": "channel-other",
                "text": "bot-secret leaked",
                "token": "bot-secret",
                "tool_trace": {"tool": "ingest", "status": "blocked"},
            },
        ]
    })


def test_backend_actions_drive_stateful_unisonai_fixture(tmp_path):
    actions = [
        {
            "op": "correct",
            "question": "What is 2 + 2?",
            "bad_answer": "5",
            "good_answer": "4",
            "territory": "arithmetic",
        },
        {
            "op": "correct",
            "question": "What is 3 + 3?",
            "bad_answer": "7",
            "good_answer": "6",
            "territory": "arithmetic",
        },
        {"op": "answer", "question": "What is 2 + 2?"},
        {
            "op": "self_play_probe",
            "question": "What is the capital of Atlantis?",
            "proposed_answer": "Poseidon City",
        },
        {
            "op": "scorecard",
            "items": [
                {
                    "id": "fixed-001",
                    "model_ref": "scripted:model",
                    "answer": "4",
                    "expected": "4",
                },
                {
                    "id": "fixed-002",
                    "model_ref": "scripted:model",
                    "answer": "blue",
                    "expected": "red",
                },
            ],
        },
        {
            "op": "scorecard",
            "items": [
                {
                    "id": "fixed-001",
                    "model_ref": "scripted:model",
                    "answer": "4",
                    "expected": "4",
                },
                {
                    "id": "fixed-002",
                    "model_ref": "scripted:model",
                    "answer": "blue",
                    "expected": "red",
                },
            ],
        },
        {
            "op": "discord_ingest",
            "configured_channel": "channel-allowed",
            "channel_id": "channel-allowed",
            "text": "Document received; tool trace attached.",
            "token": "bot-secret",
            "tool_trace": {"tool": "ingest", "status": "ok"},
        },
        {
            "op": "discord_ingest",
            "configured_channel": "channel-allowed",
            "channel_id": "channel-other",
            "text": "bot-secret leaked",
            "token": "bot-secret",
            "tool_trace": {"tool": "ingest", "status": "blocked"},
        },
    ]

    result = run_unisonai_stateful_backend_benchmark(
        ScriptedBackend(json.dumps({"actions": actions})),
        tmp_path,
    )

    assert result["passed"] is True
    assert result["pass_rate"] == 1.0
    assert result["backend_name"] == "scripted-unison"
    assert result["model_ref"] == "scripted:model"
    assert result["action_count"] == len(actions)
    assert result["receipts"]["event_count"] >= len(actions)


def test_backend_actions_fail_closed_on_unstructured_text(tmp_path):
    result = run_unisonai_stateful_backend_benchmark(
        ScriptedBackend("I would update memory and check Discord scope."),
        tmp_path,
    )

    assert result["passed"] is False
    assert result["pass_rate"] == 0.0
    assert result["failure_class"] == "malformed_action_json"


def test_backend_repair_json_preserves_receipts_and_scores_repaired_actions(tmp_path):
    backend = SequenceBackend([
        "I can do this with memory actions, but here is prose first.",
        _actions_json(),
    ])

    result = run_unisonai_stateful_backend_benchmark(
        backend,
        tmp_path,
        repair_json=True,
    )

    assert result["passed"] is True
    assert result["failure_class"] == "none"
    assert result["repair"]["attempted"] is True
    assert result["repair"]["succeeded"] is True
    assert result["repair"]["raw_response_sha256"]
    assert result["repair"]["repair_response_sha256"]
    assert backend.calls == 2


def test_backend_repair_json_fails_closed_when_repair_is_not_actions(tmp_path):
    result = run_unisonai_stateful_backend_benchmark(
        SequenceBackend([
            "I would update memory and check Discord scope.",
            "Still prose; no executable actions.",
        ]),
        tmp_path,
        repair_json=True,
    )

    assert result["passed"] is False
    assert result["pass_rate"] == 0.0
    assert result["failure_class"] == "malformed_action_json"
    assert result["repair"]["attempted"] is True
    assert result["repair"]["succeeded"] is False


def test_backend_repair_json_rejects_empty_action_list(tmp_path):
    result = run_unisonai_stateful_backend_benchmark(
        SequenceBackend([
            "I would update memory and check Discord scope.",
            "{\"actions\": []}",
        ]),
        tmp_path,
        repair_json=True,
    )

    assert result["passed"] is False
    assert result["pass_rate"] == 0.0
    assert result["failure_class"] == "malformed_action_json"
    assert result["repair"]["attempted"] is True
    assert result["repair"]["succeeded"] is False


def test_stateful_runner_accepts_scripted_backend_actions(tmp_path):
    actions_path = tmp_path / "actions.json"
    out_path = tmp_path / "out.json"
    actions_path.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "op": "correct",
                        "question": "What is 2 + 2?",
                        "bad_answer": "5",
                        "good_answer": "4",
                        "territory": "arithmetic",
                    },
                    {
                        "op": "correct",
                        "question": "What is 3 + 3?",
                        "bad_answer": "7",
                        "good_answer": "6",
                        "territory": "arithmetic",
                    },
                    {"op": "answer", "question": "What is 2 + 2?"},
                    {
                        "op": "self_play_probe",
                        "question": "What is the capital of Atlantis?",
                        "proposed_answer": "Poseidon City",
                    },
                    {
                        "op": "scorecard",
                        "items": [
                            {
                                "id": "fixed-001",
                                "model_ref": "scripted:model",
                                "answer": "4",
                                "expected": "4",
                            },
                            {
                                "id": "fixed-002",
                                "model_ref": "scripted:model",
                                "answer": "blue",
                                "expected": "red",
                            },
                        ],
                    },
                    {
                        "op": "scorecard",
                        "items": [
                            {
                                "id": "fixed-001",
                                "model_ref": "scripted:model",
                                "answer": "4",
                                "expected": "4",
                            },
                            {
                                "id": "fixed-002",
                                "model_ref": "scripted:model",
                                "answer": "blue",
                                "expected": "red",
                            },
                        ],
                    },
                    {
                        "op": "discord_ingest",
                        "configured_channel": "channel-allowed",
                        "channel_id": "channel-allowed",
                        "text": "Document received; tool trace attached.",
                        "token": "bot-secret",
                        "tool_trace": {"tool": "ingest", "status": "ok"},
                    },
                    {
                        "op": "discord_ingest",
                        "configured_channel": "channel-allowed",
                        "channel_id": "channel-other",
                        "text": "bot-secret leaked",
                        "token": "bot-secret",
                        "tool_trace": {"tool": "ingest", "status": "blocked"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    assert main([
        "--backend-actions-json",
        str(actions_path),
        "--state-root",
        str(tmp_path / "state"),
        "--out",
        str(out_path),
    ]) == 0
    result = json.loads(out_path.read_text(encoding="utf-8"))
    assert result["schema"] == "unisonai.stateful-backend-benchmark/v1"
    assert result["passed"] is True


def test_stateful_runner_builds_dry_provider_matrix(tmp_path):
    out_path = tmp_path / "matrix.json"
    markdown_path = tmp_path / "matrix.md"

    assert main([
        "--providers",
        "dry",
        "--state-root",
        str(tmp_path / "state"),
        "--out",
        str(out_path),
        "--markdown-out",
        str(markdown_path),
    ]) == 0

    result = json.loads(out_path.read_text(encoding="utf-8"))
    assert result["schema"] == "unisonai.stateful-provider-matrix/v1"
    assert result["provider_roles_requested"] == ["dry_fixture"]
    assert result["provider_aliases"]["dry"] == "dry_fixture"
    assert result["summary"]["provider_role_ids"] == ["dry_fixture"]
    assert result["summary"]["operational_rows"] == 1
    assert result["summary"]["mean_pass_rate"] == 1.0
    assert result["rows"][0]["provider"] == "dry"
    assert result["rows"][0]["provider_role"] == "dry_fixture"
    assert result["rows"][0]["passed"] is True
    assert result["rows"][0]["pass_rate"] == 1.0
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# UnisonAI Stateful Provider Matrix" in markdown
    assert "| dry | dry_fixture | false | true | true | 1.0 | none | 8 |" in markdown
