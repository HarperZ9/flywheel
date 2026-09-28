"""Suite-wide isolation: no test may ever touch the operator's real run
root, home store, or OS credential store. A bare `_Handler.__new__` in a
route test inherits the class-level `run_root` default (the REAL run root) —
twice now a new write path turned that into stub runs landing in real
history. These fixtures remove the failure mode as a class instead of
patching it test by test: every test runs against a session-scoped scratch
root, and forgetting to set `h.run_root` writes there, never into E:."""

import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest


@pytest.fixture
def text_once_written():
    """Read a file a subprocess is writing, without racing its creation.

    `open(path, "w")` makes the name before any content reaches it, so a poll
    on `Path.exists()` can return the instant the file appears and read an
    empty string. The window is wide enough to have failed one windows-latest
    shard on a commit that passed the same shard on a sibling run, and the
    reads downstream of it were an equality assertion in one file and `int()`
    in another, so the same race surfaced as two unrelated-looking errors.

    Waiting for content closes it. The timeout message says whether the file
    never appeared or appeared and stayed empty, because those are different
    faults in the subprocess under test. Callers that only need the write to
    have landed pass `required=False` and get whatever is there at the
    deadline, keeping a barrier a barrier rather than an assertion.

    Whitespace does not count as content; every caller writes a repr or a pid.
    """
    def _read(path, *, timeout=30.0, why="", required=True):
        deadline = time.monotonic() + timeout
        text = ""
        while True:
            try:
                text = path.read_text(encoding="utf-8")
            except (FileNotFoundError, PermissionError):
                text = ""
            if text.strip() or time.monotonic() >= deadline:
                break
            time.sleep(0.02)
        if not text.strip() and required:
            state = "stayed empty" if path.exists() else "never appeared"
            raise AssertionError(
                f"{path} {state} within {timeout}s. {why}".strip())
        return text
    return _read


@pytest.fixture
def scratch():
    """A scratch directory shaped like the one the sandbox runner makes.

    Not `tmp_path`. A unix socket path is copied into a 108-byte kernel
    field (104 on macOS) and `bind` truncates rather than refusing, so a
    long directory produces a socket nobody can name. pytest builds its
    path out of the test's own name under a per-user temp root that is
    already about fifty bytes on macOS, which is over the line before the
    socket name is added. The runner uses `mkdtemp` with a short prefix,
    so a test that binds a socket uses the same thing.
    """
    where = Path(tempfile.mkdtemp(prefix="fw_sandbox_")).resolve()
    try:
        yield where
    finally:
        shutil.rmtree(where, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolated_run_root(tmp_path_factory, monkeypatch):
    scratch = tmp_path_factory.mktemp("run-root")
    home = tmp_path_factory.mktemp("flywheel-home")
    pip_cache = scratch / "pip-cache"
    pip_cache.mkdir()
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(scratch))
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("PIP_CACHE_DIR", str(pip_cache))
    # The lane registry path is fixed when harness.lanes is imported, which can
    # be before FLYWHEEL_HOME above is set, so it would read the owner's real
    # ~/.flywheel/lanes.json (its runtime_python pins and env_allow grants).
    try:
        from harness import lanes
        monkeypatch.setattr(lanes, "LANE_REGISTRY_PATH", home / "lanes.json")
    except Exception:
        pass  # lanes may be unimportable in a narrow slice; the env still guards
    try:
        from harness import gateway
        monkeypatch.setattr(gateway._Handler, "run_root", str(scratch),
                            raising=False)
    except Exception:
        pass  # gateway may be unimportable in narrow slices; env still guards
    yield


@pytest.fixture(scope="session", autouse=True)
def _real_home_pointer_left_alone(tmp_path_factory):
    """Fail the session if any test (a subprocess gateway included) pointed
    the owner's real home pointer at a pytest home."""
    try:
        from harness.capture_hooks import home
        real = home.pointer_path()
        before = real.read_bytes() if real and real.is_file() else None
    except Exception:
        real = None
    yield
    if real is None or not real.is_file() or real.read_bytes() == before:
        return
    named = home.read_pointer(real)
    base = Path(tmp_path_factory.getbasetemp()).resolve().parent
    if named is not None and Path(os.path.abspath(named)).is_relative_to(base):
        pytest.fail(f"a test pointed the real home pointer at a pytest home: {named}")


@pytest.fixture(autouse=True)
def _isolated_home_pointer(tmp_path_factory, monkeypatch):
    """The per-user home pointer is the owner's machine state: a hook mounted
    without --home follows it to a home. A test that starts a gateway reaches
    publish_endpoint, which rewrites it, so every test gets its own pointer
    file. gateway_endpoint_file imports the name, so both are patched."""
    target = tmp_path_factory.mktemp("home-pointer") / "home.json"
    try:
        from harness import gateway_endpoint_file
        from harness.capture_hooks import home
        monkeypatch.setattr(home, "pointer_path", lambda: target)
        monkeypatch.setattr(gateway_endpoint_file, "pointer_path", lambda: target)
    except Exception:
        pass  # the hook package may be absent in a narrow slice
    yield


@pytest.fixture(autouse=True)
def _isolated_keychain(request, monkeypatch):
    """The OS credential store is machine state, so a test that reads it is a
    test whose verdict depends on who is running it.

    Credential resolution is env-first, keychain-second. A dormancy test
    (`delenv`, then assert the slot stays off the ladder) is only honest while
    the second half stays empty: on a workstation that really has
    ANTHROPIC_API_KEY in Credential Manager, the same assertion would fail
    locally and pass in CI. Blanking `keychain_get` for the suite pins every
    resolution to the environment, which is what those tests already control.

    `@pytest.mark.real_keychain` opts back in, for the tests that exercise the
    store itself."""
    if request.node.get_closest_marker("real_keychain"):
        yield
        return
    try:
        from harness import keychain
        monkeypatch.setattr(keychain, "keychain_get", lambda _name: None)
    except Exception:
        pass  # keychain may be absent in a stripped slice; env path still holds
    yield


@pytest.fixture(autouse=True)
def _isolated_claude_cli_status(request, monkeypatch):
    """Unit tests must not read the operator's real Claude account state."""
    if request.node.get_closest_marker("real_claude_cli"):
        yield
        return
    try:
        from harness import claude_cli_auth
        monkeypatch.setattr(
            claude_cli_auth,
            "_run_status",
            lambda _argv, _timeout: type("P", (), {
                "returncode": 1,
                "stdout": '{"loggedIn": false}',
                "stderr": "",
            })(),
        )
    except Exception:
        pass
    yield


@pytest.fixture
def lanes_at_their_pins(monkeypatch):
    """Every pip or npm lane reads as installed at its pin. A lane below its pin
    does not launch, so a test that freezes a lane launch must not depend on
    which lane packages the host happens to have installed."""
    monkeypatch.setattr("harness.lanes._installed_version", lambda lane: lane.version)
