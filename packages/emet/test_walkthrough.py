# SPDX-License-Identifier: AGPL-3.0-only
import subprocess, sys, pathlib

RENDER = pathlib.Path(__file__).parent / "docs" / "rationale" / "walkthrough" / "render.py"
TRANSCRIPT = RENDER.parent / "transcript.txt"

def test_transcript_regenerates_and_matches_committed():
    # Regenerate, then --check asserts committed == freshly rendered (no drift).
    subprocess.run([sys.executable, str(RENDER)], check=True)
    r = subprocess.run([sys.executable, str(RENDER), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

def test_transcript_is_deterministic():
    subprocess.run([sys.executable, str(RENDER)], check=True)
    t1 = TRANSCRIPT.read_text(encoding="utf-8")
    subprocess.run([sys.executable, str(RENDER)], check=True)
    t2 = TRANSCRIPT.read_text(encoding="utf-8")
    assert t1 == t2, "render.py is not deterministic"


if __name__ == "__main__":
    # Self-running, matching the repo's other test files (python test_*.py).
    test_transcript_regenerates_and_matches_committed()
    test_transcript_is_deterministic()
    print("test_walkthrough: 2 passed")
