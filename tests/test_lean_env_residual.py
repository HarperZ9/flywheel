"""What the Lean spawn allowlist leaves open, pinned so the texts cannot drift.

lean_env() empties the Lean process's own environment. It does nothing to
the process that started Lean. That process is the harness, its environment
holds every variable the allowlist removed, and this user can read it: on
Windows out of the process's memory (psutil), on Linux from
/proc/<pid>/environ, which holds the environment a process started with.

The live test starts a harness process with a synthetic variable set when it
starts, and gives lean_check a candidate that runs a helper walking its
ancestors. It asserts the value still reaches the receipt, which is what the
does_not_prove line, lean_env.py and docs/PROOF-AND-FORMATS.md say. If Lean
comes to run isolated from this user's processes, this test fails; update
those texts with it. Assertions read booleans only.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from harness.lean_oracle import leanchecker_available

PROBE = "FLYWHEEL_PROBE_SECRET"
VALUE = "probe-value-123"
ROOT = Path(__file__).resolve().parents[1]

# Walk the ancestors and print the probe value wherever one holds it. psutil
# where it is installed; /proc on Linux without it.
HELPER = '''import os
K = "FLYWHEEL_PROBE_SECRET"


def with_psutil(psutil):
    for proc in psutil.Process().parents():
        try:
            yield proc.environ().get(K)
        except Exception:
            yield None


def with_proc():
    pid = os.getppid()
    while pid > 1:
        try:
            with open("/proc/%d/environ" % pid, "rb") as fh:
                entries = fh.read().split(bytes(1))
            with open("/proc/%d/stat" % pid) as fh:
                stat = fh.read()
        except OSError:
            return
        for entry in entries:
            if entry.startswith(K.encode() + b"="):
                yield entry.split(b"=", 1)[1].decode()
        pid = int(stat.rsplit(")", 1)[1].split()[1])


try:
    import psutil
    found = with_psutil(psutil)
except ImportError:
    found = with_proc()
for value in found:
    if value:
        print("ancestor holds", value)
'''

# The harness process: the probe is in its environment from the start, the
# way an exported secret is. It prints booleans, never the receipt.
HARNESS = (
    "import json, sys\n"
    "from harness.lean_oracle import lean_check\n"
    "doc = lean_check(open(sys.argv[1], encoding='utf-8').read())\n"
    f"print(json.dumps({{'passed': doc['passed'], "
    f"'leaked': {VALUE!r} in json.dumps(doc)}}))\n")


def _route_available() -> bool:
    if sys.platform.startswith("linux"):
        return Path("/proc/self/environ").exists()
    try:
        import psutil  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.timeout(240)
@pytest.mark.skipif(not leanchecker_available(),
                    reason="lean or its leanchecker not installed")
@pytest.mark.skipif(not _route_available(),
                    reason="no psutil and no /proc to read an ancestor with")
def test_live_an_ancestor_environment_read_still_reaches_the_receipt(
        tmp_path):
    helper = tmp_path / "ancestors.py"
    helper.write_text(HELPER, encoding="utf-8")
    exe, script = (Path(sys.executable).as_posix(), helper.as_posix())
    candidate = tmp_path / "candidate.lean"
    candidate.write_text(
        "#eval do\n"
        f'  let out ← IO.Process.output {{ cmd := "{exe}", '
        f'args := #["{script}"] }}\n'
        "  IO.println out.stdout\n"
        "theorem probe_ok : 1 + 1 = 2 := rfl\n", encoding="utf-8")
    env = {**os.environ, PROBE: VALUE}
    done = subprocess.run([sys.executable, "-c", HARNESS, str(candidate)],
                          cwd=str(ROOT), env=env, capture_output=True,
                          text=True, timeout=200)
    assert done.returncode == 0, done.stderr[-800:]
    got = json.loads(done.stdout.strip().splitlines()[-1])
    assert got["passed"] is True, got
    assert got["leaked"] is True, (
        "the ancestor environment read no longer reaches the receipt; if Lean "
        "now runs isolated, update lean_env.py, the _ENVIRONMENT line and "
        "docs/PROOF-AND-FORMATS.md, then this test")


def test_the_texts_name_the_ancestor_route():
    from harness import lean_env
    from harness.lean_oracle_adapter import _ENVIRONMENT
    assert "the process that started Lean" in _ENVIRONMENT
    assert "the process that started Lean" in lean_env.__doc__
    doc = (ROOT / "docs" / "PROOF-AND-FORMATS.md").read_text(encoding="utf-8")
    assert "the process that started Lean" in doc
