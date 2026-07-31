"""run_demo_pool.py's fenced-JSON extraction wiring, end to end against a
FAKE proposer -- no network. Separate file from test_run_demo_pool.py so
that file stays under the 300-line file gate (scripts/check_file_gate.py).

Covers the two things the extraction fix must prove beyond
tests/test_fenced_extract.py's unit coverage of the extractor itself:

  1. run_fill() actually wires ExtractingProposer in, so a fenced response
     is stored (content-addressed by harness/pool.py, unmodified) as its
     EXTRACTED body, not the raw fenced text.
  2. the raw response is not silently discarded: it is recoverable from
     <out_dir>/raw_candidates/ via the sidecar extraction_log.json, and the
     run manifest declares which extraction policy ran.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "run_demo_pool", ROOT / "scripts" / "run_demo_pool.py")
RDP = importlib.util.module_from_spec(_spec)
sys.modules["run_demo_pool"] = RDP   # dataclass field resolution needs this
_spec.loader.exec_module(RDP)

from harness.pool import Pool  # noqa: E402


class FencedFakeProposer:
    """Every response comes back wrapped in a markdown ```json fence, the
    exact shape the live pilot actually returned from qwen2.5:0.5b."""

    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, seed, temperature, max_new_tokens):
        self.calls.append((prompt, seed, temperature, max_new_tokens))
        body = json.dumps({"seed": seed, "prompt_len": len(prompt)})

        class R:
            text = f"```json\n{body}\n```"
        return R()


def fake_fetch(version="0.32.3", quantization="Q4_K_M", model="qwen2.5:0.5b",
               digest="deadbeef" * 8):
    def fetch(path, payload=None):
        if path == "/api/version":
            return {"version": version}
        if path == "/api/show":
            return {"details": {"quantization_level": quantization,
                                "format": "gguf", "parameter_size": "0.5B"}}
        if path == "/api/tags":
            return {"models": [{"name": model, "model": model, "digest": digest}]}
        raise AssertionError(f"unexpected path {path!r}")
    return fetch


def test_a_fenced_response_is_stored_as_its_extracted_body_not_the_raw_fence(tmp_path):
    result = RDP.run_fill(
        family="zarankiewicz", rung="qwen2.5:0.5b", out_base=tmp_path,
        confirmatory=False, pilot=True, limit=1, reason="extraction test",
        fetch=fake_fetch(), proposer=FencedFakeProposer())

    pool = Pool(result["out_dir"])
    task_id = pool.task_ids()[0]
    for slot, text in pool.candidates(task_id):
        assert not text.startswith("```")
        obj = json.loads(text)          # would raise if the fence survived
        assert "seed" in obj


def test_the_run_manifest_declares_the_extraction_policy_name(tmp_path):
    result = RDP.run_fill(
        family="zarankiewicz", rung="qwen2.5:0.5b", out_base=tmp_path,
        confirmatory=False, pilot=True, limit=1, reason="extraction test",
        fetch=fake_fetch(), proposer=FencedFakeProposer())

    assert result["manifest"]["extraction"] == "fenced-json-v1"
    on_disk = json.loads(
        Path(result["out_dir"], "run_manifest.json").read_text(encoding="utf-8"))
    assert on_disk["extraction"] == "fenced-json-v1"


def test_extraction_log_carries_both_raw_and_extracted_forms_per_slot(tmp_path):
    result = RDP.run_fill(
        family="zarankiewicz", rung="qwen2.5:0.5b", out_base=tmp_path,
        confirmatory=False, pilot=True, limit=1, reason="extraction test",
        fetch=fake_fetch(), proposer=FencedFakeProposer())

    out_dir = Path(result["out_dir"])
    log = json.loads((out_dir / "extraction_log.json").read_text(encoding="utf-8"))
    assert log["policy"] == "fenced-json-v1"
    assert len(log["records"]) == 4          # K=4 slots for the one task

    pool = Pool(out_dir)
    task_id = pool.task_ids()[0]
    stored = {s["slot"]: s["candidate_sha256"] for s in pool.slots(task_id)}

    for rec in log["records"]:
        assert rec["fence_found"] is True
        assert rec["fence_count"] == 1
        # the extracted digest in the sidecar matches what pool.py actually
        # stored as the candidate for that slot
        assert rec["extracted_sha256"] == stored[rec["slot"]]
        # the raw fenced text is recoverable, verbatim, from its own digest
        raw_name = rec["raw_sha256"].split(":", 1)[1]
        raw_path = out_dir / "raw_candidates" / f"{raw_name}.txt"
        assert raw_path.is_file()
        assert raw_path.read_text(encoding="utf-8").startswith("```json\n")
        assert raw_path.read_text(encoding="utf-8").rstrip().endswith("```")
        # and it hashes to its own claimed digest -- the same discipline
        # Pool.text() already enforces for the extracted store
        import hashlib
        raw_bytes = raw_path.read_text(encoding="utf-8").encode("utf-8")
        assert hashlib.sha256(raw_bytes).hexdigest() == raw_name


def test_a_bare_unfenced_fake_response_still_round_trips_unchanged(tmp_path):
    """Regression guard: the pre-existing FakeProposer shape used throughout
    tests/test_run_demo_pool.py (plain, unfenced .text) must still work
    identically once every response passes through the extractor -- no
    fence means no change."""

    class PlainFakeProposer:
        def generate(self, prompt, *, seed, temperature, max_new_tokens):
            class R:
                text = f"CERT seed={seed} temp={temperature} len={len(prompt)}"
            return R()

    result = RDP.run_fill(
        family="zarankiewicz", rung="qwen2.5:0.5b", out_base=tmp_path,
        confirmatory=False, pilot=True, limit=1, reason="passthrough test",
        fetch=fake_fetch(), proposer=PlainFakeProposer())

    pool = Pool(result["out_dir"])
    task_id = pool.task_ids()[0]
    for slot, text in pool.candidates(task_id):
        assert text.startswith("CERT seed=")

    log = json.loads(
        Path(result["out_dir"], "extraction_log.json")
        .read_text(encoding="utf-8"))
    assert all(rec["fence_found"] is False for rec in log["records"])


def test_a_generation_failure_still_records_error_with_extraction_in_the_loop(tmp_path):
    """The extraction wrapper must not swallow or alter pool.fill's own
    failure-recording contract for slots where generation itself raised."""

    class FlakyProposer:
        def generate(self, prompt, *, seed, temperature, max_new_tokens):
            if seed == 42:
                raise RuntimeError("simulated generation failure")

            class R:
                text = f"```json\n{{\"seed\": {seed}}}\n```"
            return R()

    result = RDP.run_fill(
        family="zarankiewicz", rung="qwen2.5:0.5b", out_base=tmp_path,
        confirmatory=False, pilot=True, limit=1, reason="failure test",
        fetch=fake_fetch(), proposer=FlakyProposer())

    pool = Pool(result["out_dir"])
    task_id = pool.task_ids()[0]
    slots = pool.slots(task_id)
    failed = [s for s in slots if s["seed"] == 42]
    assert failed and failed[0]["candidate_sha256"] is None
    assert "simulated generation failure" in failed[0]["error"]

    log = json.loads(
        Path(result["out_dir"], "extraction_log.json")
        .read_text(encoding="utf-8"))
    # only the 3 successful slots got an extraction record; the failed one
    # (seed 42 is slot index 1 -- see SEEDS in run_demo_pool.py) never
    # produced raw text to extract from
    assert len(log["records"]) == 3
    failed_slot_index = failed[0]["slot"]
    assert failed_slot_index not in {r["slot"] for r in log["records"]}
