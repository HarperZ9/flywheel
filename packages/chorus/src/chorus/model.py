"""model.py -- the optional model seam for the sentiment overlay (zero-dep edge).

chorus stays standalone: it does not import a model client. A model is any callable
that takes a list of comment texts and returns a list of ``{compound, label}`` dicts.
SubprocessModel is the shipped edge: it shells a command once with the texts as JSON
on stdin and reads the JSON array back, so a caller can wire any model (the Flywheel
router, an LLM CLI) without chorus depending on it. The model overlay is advisory and
provenance-tagged; it never enters the re-checkable digest core.
"""
from __future__ import annotations

import json
import subprocess


class SubprocessModel:
    """Call an external model command: texts (JSON array) in, ``[{compound,label}]`` out."""

    def __init__(self, argv: list[str], *, ref: str, timeout: float = 120.0) -> None:
        self.argv = list(argv)
        self.ref = ref
        self.timeout = timeout

    def __call__(self, texts: list[str]) -> list[dict]:
        proc = subprocess.run(self.argv, input=json.dumps(texts), capture_output=True,
                              text=True, timeout=self.timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"model exit {proc.returncode}: {(proc.stderr or '').strip()[:200]}")
        result = json.loads(proc.stdout)
        if not isinstance(result, list):
            raise ValueError("model did not return a JSON list")
        return result
