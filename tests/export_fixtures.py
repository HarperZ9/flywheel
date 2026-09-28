"""Planted custody for the export tests: a gateway trace (with a personal
data hit), a captured turn whose text names the home directory, and an
imported Claude Code transcript holding a fake credential. No real data."""
from __future__ import annotations

import contextlib
import json
from pathlib import Path

from delete_fixtures import OWNER, plant_trace, plant_turn
from import_fixtures import SESSION, age_tree, claude_tree
from trace_enc_fakes import StreamTestProvider, using
from trace_redact_fakes import credential_fakes

TOKEN = credential_fakes()["github_token"]
EMAIL = "reach.me@example.com"


def home_text() -> str:
    return str(Path.home())


@contextlib.contextmanager
def planted(tmp_path, monkeypatch):
    """(home, refs) with every exported store holding one item."""
    from harness import trace_witness
    from harness.trace_import_claude import plan_claude
    from harness.trace_import_core import run_import
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "run"))
    monkeypatch.setattr(trace_witness, "default_sink", trace_witness.MemorySink)
    for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        monkeypatch.delenv(name, raising=False)
    with using(StreamTestProvider()):
        trace = plant_trace(home, text="final answer, write to " + EMAIL)
        turn = plant_turn(home, text="look in " + home_text() + " for the notes")
        root, _, _ = claude_tree(tmp_path)
        transcript = root / "projects" / "C--work-demo" / f"{SESSION}.jsonl"
        with open(transcript, "ab") as stream:
            stream.write(json.dumps({"type": "user", "message": {
                "content": "my token is " + TOKEN}}).encode() + b"\n")
        age_tree(root, seconds=300)
        run_import(home, plan_claude(home, root=root))
        yield home, {"trace": trace, "turn": turn["turn_ref"]}


def export_bytes(out: Path) -> bytes:
    return b"".join(p.read_bytes() for p in sorted(out.rglob("*")) if p.is_file())
