"""chorus_bridge.py -- drive the `chorus` discourse satellite over a gathered corpus.

chorus reads a corpus of comments and threads (a gather corpus directory, or a
JSON list of gather-style rows) and emits a weighted, clustered, re-checkable
discourse digest: the themes people are actually voicing, ranked by engagement and
sentiment, each theme carrying its distribution and its surfaced dissent, and the
whole digest carrying a receipt a stranger can re-run. This bridge shells the
installed `chorus` CLI and returns its JSON digest verbatim, receipt included, so
the desktop reads chorus's own answer, never a reconstruction. A missing CLI or a
bad corpus is a named error; nothing is synthesized until a view asks.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

_TIMEOUT = 120


def _chorus_argv() -> "list | None":
    """The argv that runs the chorus CLI: the console script if on PATH, else
    `python -m chorus` if the module is importable. None when neither works."""
    exe = shutil.which("chorus")
    if exe:
        return [exe]
    try:
        import importlib.util
        if importlib.util.find_spec("chorus") is not None:
            return [sys.executable, "-m", "chorus"]
    except Exception:
        pass
    return None


def chorus_available() -> bool:
    return _chorus_argv() is not None


def discourse_digest(corpus: str, *, runner=None) -> dict:
    """Run the chorus lens over a gathered corpus. Returns the digest under
    ``result`` (with its re-checkable receipt and its verified flag), or a named
    error. ``runner`` is injectable for tests: a callable (cmd)->(rc, out, err)."""
    if not corpus or not Path(corpus).exists():
        return {"error": f"corpus not found: {corpus}"}
    argv = _chorus_argv()
    if argv is None:
        return {"error": "the chorus satellite is not installed; pip install chorus-discourse"}
    cmd = argv + ["run", str(corpus), "--verify"]
    try:
        if runner is not None:
            rc, out, err = runner(cmd)
        else:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT)
            rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return {"error": f"chorus timed out after {_TIMEOUT}s"}
    except (OSError, ValueError) as e:
        return {"error": f"{type(e).__name__}: {e}"}
    if rc != 0:
        tail = (err or out or "").strip()[-300:]
        return {"error": f"chorus failed (rc {rc}): {tail}"}
    try:
        digest = json.loads(out)
    except ValueError:
        return {"error": "chorus did not emit JSON"}
    return {"schema": "flywheel.discourse-digest/v1", "corpus": str(corpus),
            "verified": bool(digest.get("verified")), "result": digest}


def list_corpora(root: str, *, runner=None) -> dict:
    """List gather corpora under ``root`` as discourse sources, via `chorus corpora`.
    Returns ``{schema, root, corpora: [...]}`` (each corpus with its comment count and
    subject) or a named error. ``runner`` is injectable for tests."""
    if not root or not Path(root).is_dir():
        return {"error": f"root is not an existing directory: {root}"}
    argv = _chorus_argv()
    if argv is None:
        return {"error": "the chorus satellite is not installed; pip install chorus-discourse"}
    cmd = argv + ["corpora", str(root)]
    try:
        if runner is not None:
            rc, out, err = runner(cmd)
        else:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT)
            rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return {"error": f"chorus corpora timed out after {_TIMEOUT}s"}
    except (OSError, ValueError) as e:
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        result = json.loads(out) if (out or "").strip() else {}
    except ValueError:
        return {"error": f"chorus corpora did not emit JSON (rc {rc}): {(err or '').strip()[-200:]}"}
    if isinstance(result, dict) and "error" in result:   # a bad root: chorus names it, exit 1
        return result
    if rc != 0:
        return {"error": f"chorus corpora failed (rc {rc}): {(err or out or '').strip()[-200:]}"}
    return {"schema": "flywheel.discourse-corpora/v1", "root": str(root),
            "corpora": result.get("corpora", [])}
