"""Suite-wide isolation: no test may ever touch the operator's real run
root, home store, or OS credential store. A bare `_Handler.__new__` in a
route test inherits the class-level `run_root` default (the REAL run root) —
twice now a new write path turned that into stub runs landing in real
history. These fixtures remove the failure mode as a class instead of
patching it test by test: every test runs against a session-scoped scratch
root, and forgetting to set `h.run_root` writes there, never into E:."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_run_root(tmp_path_factory, monkeypatch):
    scratch = tmp_path_factory.mktemp("run-root")
    home = tmp_path_factory.mktemp("flywheel-home")
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(scratch))
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    try:
        from harness import gateway
        monkeypatch.setattr(gateway._Handler, "run_root", str(scratch),
                            raising=False)
    except Exception:
        pass  # gateway may be unimportable in narrow slices; env still guards
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
