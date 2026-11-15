#!/usr/bin/env python3
# Best-effort demo - not runtime-verified by author.
"""End-to-end demo for context-curator-lite.

Creates a small sample workspace, runs the real curation pipeline via
``context_curator_lite.curator.main``, and prints the generated bundle.
Also shows the standalone redaction/classification helpers.

Run from the repo root with the package installed, or against the source tree:

    python examples/demo.py
    # or, without installing:
    PYTHONPATH=src python examples/demo.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from context_curator_lite import curator


SAMPLE_NOTES = """\
# Plan notes
todo: next action is to finish the migration and push the branch
blocker: the integration test failed on the worktree
architecture: design invariant for the curator whitepaper
contact me at jane.doe@example.com or token=demo-secret-value
just a plain chatter line with nothing useful to extract here
"""

SAMPLE_SESSION = """\
{"role": "user", "text": "resume the handoff: continue the roadmap for the repo"}
{"role": "assistant", "text": "no keywords on this line, pure chatter"}
"""


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ccl-demo-") as tmp:
        workspace = Path(tmp)
        src = workspace / "proj"
        src.mkdir()
        (src / "notes.md").write_text(SAMPLE_NOTES, encoding="utf-8")
        (src / "session.jsonl").write_text(SAMPLE_SESSION, encoding="utf-8")

        out_dir = workspace / "artifacts"

        print("=== helper functions ===")
        print("classify(blocker...):", curator.classify("blocker: build failed"))
        print("classify(architecture...):", curator.classify("architecture plan overview"))
        print(
            "scrub(secret line):",
            curator.scrub("reach me at jane@example.com token=ghp_" + "A" * 36),
        )
        print("stable_id('notes.md'):", curator.stable_id("notes.md"))

        print("\n=== running curator.main() ===")
        exit_code = curator.main(
            roots=[str(src)],
            out_dir=str(out_dir),
            limit=50,
            per_file_limit=5,
            telos_envelope=True,
        )
        print("exit code:", exit_code)

        print("\n=== files written to out-dir ===")
        for path in sorted(out_dir.iterdir()):
            print("-", path.name)

        jsonl = next(out_dir.glob("curated-session-context-*.jsonl"))
        print("\n=== JSONL bundle ===")
        print(jsonl.read_text(encoding="utf-8").rstrip())

        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
