"""Discovery must not allocate a console or change its command contract."""
from types import SimpleNamespace

import pytest

from harness import lane_runtime_support as support


@pytest.mark.parametrize("platform,expected", [("nt", 0x08000000), ("posix", 0)])
@pytest.mark.parametrize("probe", ["npm", "python"])
def test_discovery_process_does_not_create_windows_console(monkeypatch, platform,
                                                          expected, probe):
    calls = []
    monkeypatch.setattr(support, "os", SimpleNamespace(name=platform))
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="2.0.0\n")
    monkeypatch.setattr(support.subprocess, "run", run)
    if probe == "npm":
        support._npm_global_root.cache_clear()
        try:
            assert support._npm_global_root() is not None
        finally:
            support._npm_global_root.cache_clear()
        command, options = calls[0]
        assert command == ["npm.cmd" if platform == "nt" else "npm", "root", "-g"]
        assert options["timeout"] == 20
    else:
        lane = SimpleNamespace(kind="pip", install_name="synthetic-package")
        assert support.package_runtime_version(lane, "owned-python.exe") == "2.0.0"
        command, options = calls[0]
        assert command[:3] == ["owned-python.exe", "-I", "-c"]
        assert command[-1] == "synthetic-package"
        assert options["timeout"] == 8
    assert options["creationflags"] == expected
    assert options["capture_output"] is True
    assert options["text"] is True
    assert not options.get("shell", False)
