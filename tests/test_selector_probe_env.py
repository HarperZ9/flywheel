"""The selector's behavioral probe runs model-written code, so its child
starts from the oracle allowlist (oracle.run_env), not the harness's own
environment.

A candidate's return values become its signature. The selection receipt
stores hashes, indices and confidence, not signatures, so a value a
candidate read from the environment did not reach a stored receipt. The
candidate could still send the value anywhere else its process can reach.
The probe variable here is synthetic.
"""
from harness import selector_probe
from harness.oracle import ENV_ALLOWLIST

PROBE = "FLYWHEEL_PROBE_SECRET"
VALUE = "probe-value-123"
READER = ("import os\n"
          "def f(x):\n"
          f"    return os.environ.get({PROBE!r})\n")


def test_probe_child_gets_the_oracle_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv(PROBE, VALUE)
    seen = []

    class _Proc:
        returncode = 0

        def communicate(self, timeout=None):
            return b'["1"]\n', b""

    def spawn(argv, **kw):
        seen.append(kw.get("env"))
        return _Proc()
    monkeypatch.setattr(selector_probe, "spawn_killable", spawn)
    sig = selector_probe._signature("def f(x):\n    return x\n", "f", [(1,)],
                                    tmp_path / "w", 0)
    assert sig == ("1",)
    # Key names and booleans only, so a failure report never prints a value
    # from the harness environment.
    (env,) = seen
    assert env is not None
    extra = sorted(set(env) - ENV_ALLOWLIST
                   - {"PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED"})
    assert not extra, extra
    leaked = PROBE in env
    assert not leaked
    # Set iteration order stays pinned, so signatures match across runs.
    pinned = env.get("PYTHONHASHSEED") == "0"
    assert pinned


def test_a_candidate_reading_a_harness_variable_sees_nothing(monkeypatch,
                                                             tmp_path):
    monkeypatch.setenv(PROBE, VALUE)
    sig = selector_probe._signature(READER, "f", [(1,)], tmp_path / "w", 0)
    assert sig == ("None",), sig
