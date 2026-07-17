"""Suite-wide isolation: no test may ever touch the operator's real run
root or home store. A bare `_Handler.__new__` in a route test inherits the
class-level `run_root` default (the REAL run root) — twice now a new write
path turned that into stub runs landing in real history. This fixture
removes the failure mode as a class instead of patching it test by test:
every test runs against a session-scoped scratch root, and forgetting to
set `h.run_root` writes there, never into E:."""

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
