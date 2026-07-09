"""Fast falsifiers for the zero-dependency demo recorder. No network."""

import copy
import json
import re
from pathlib import Path

from scripts.demo_player_html import render_player_html
from scripts.demo_recorder import (
    TRANSCRIPT_SCHEMA,
    build_transcript,
    execute_step,
    load_demo_script,
    record_demo,
    transcript_receipt,
)

SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
EXTERNAL_URL_ATTR = re.compile(r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//""", re.IGNORECASE)


def write_script(tmp_path: Path, steps: list[dict]) -> Path:
    path = tmp_path / "demo-script.json"
    path.write_text(json.dumps({"steps": steps}), encoding="utf-8")
    return path


def sample_steps() -> list[dict]:
    return [
        {
            "title": "Say hello",
            "command": 'python -c "print(\'hello from the demo\')"',
            "narration": "A tiny local machine says hello.",
        },
        {
            "title": "Count to three",
            "command": 'python -c "print(1); print(2); print(3)"',
            "narration": "It can count too.",
        },
    ]


def test_dry_run_produces_valid_transcript_and_player(tmp_path):
    script = write_script(tmp_path, sample_steps())
    result = record_demo(script, "dry-demo", out_root=tmp_path / "demos", dry_run=True)

    transcript_path = Path(result["transcript_path"])
    player_path = Path(result["player_path"])
    assert transcript_path.exists()
    assert player_path.exists()

    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    assert transcript["schema"] == TRANSCRIPT_SCHEMA
    assert transcript["dry_run"] is True
    assert transcript["step_count"] == 2
    assert SHA256_HEX.match(transcript["receipt_sha256"])
    for step in transcript["steps"]:
        assert step["mode"] == "dry-run"
        assert step["exit_code"] == 0
        assert "[dry-run] command not executed" in step["output"]
        assert SHA256_HEX.match(step["output_sha256"])
        assert step["output_sha256"] != transcript["receipt_sha256"]

    html_text = player_path.read_text(encoding="utf-8")
    assert "dry-demo" in html_text
    assert 'id="transcript-data"' in html_text
    assert "Play" in html_text and "Restart" in html_text


def test_transcript_receipt_changes_when_output_changes(tmp_path):
    script = write_script(tmp_path, sample_steps())
    baseline = record_demo(script, "hash-demo", out_root=tmp_path / "demos", dry_run=True)
    steps = baseline["transcript"]["steps"]

    mutated = copy.deepcopy(steps)
    mutated[0]["output"] = mutated[0]["output"] + " tampered"

    assert transcript_receipt(steps) == baseline["transcript"]["receipt_sha256"]
    assert transcript_receipt(mutated) != transcript_receipt(steps)
    assert (
        build_transcript("hash-demo", mutated, dry_run=True)["receipt_sha256"]
        != baseline["transcript"]["receipt_sha256"]
    )


def test_failing_command_records_exit_code_honestly():
    step = {
        "title": "Deliberate failure",
        "command": 'python -c "import sys; print(\'boom\'); sys.exit(3)"',
        "narration": "Failures get recorded, not hidden.",
    }
    result = execute_step(step, index=0, dry_run=False, timeout_seconds=30.0)

    assert result["exit_code"] == 3
    assert "boom" in result["output"]
    assert result["mode"] == "live"
    assert SHA256_HEX.match(result["output_sha256"])


def test_player_html_has_no_external_urls(tmp_path):
    script = write_script(tmp_path, sample_steps())
    result = record_demo(script, "offline-demo", out_root=tmp_path / "demos", dry_run=True)
    html_text = Path(result["player_path"]).read_text(encoding="utf-8")

    assert EXTERNAL_URL_ATTR.search(html_text) is None
    for attr_match in re.finditer(r"""(?:src|href)\s*=\s*["']([^"']*)["']""", html_text):
        assert not attr_match.group(1).lower().startswith(("http://", "https://", "//"))


def test_load_demo_script_rejects_incomplete_steps(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{"title": "no command", "narration": "x"}]), encoding="utf-8")
    try:
        load_demo_script(path)
    except ValueError as exc:
        assert "command" in str(exc)
    else:
        raise AssertionError("expected ValueError for a step without a command")
