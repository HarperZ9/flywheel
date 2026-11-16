from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from desktop.tool.rowan_tts.jobs import RowanTtsState


class _EarlyFailureEngine:
    backend = "fake-early-failure"
    resident = False

    def synthesize(self, **_: Any) -> dict[str, Any]:
        raise RuntimeError("fake engine failed before returning metadata")


def test_early_engine_failure_does_not_fabricate_model_identity(tmp_path: Path):
    state = RowanTtsState(
        engine=_EarlyFailureEngine(),
        out_dir=tmp_path,
        token="test-token",
    )
    try:
        job = state.submit({"text": "fail before metadata", "seed": 9})
        state.wait(job, 3)

        assert job.state == "failed"
        assert job.engine_meta is None
        payload = json.loads(job.manifest_path.read_text(encoding="utf-8"))
        assert payload["model"] is None
        assert payload["model_observed"] is False
        assert payload["model_observation_basis"] == "unobserved_engine_metadata"
        assert "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign" not in json.dumps(payload)
    finally:
        state.stop()
