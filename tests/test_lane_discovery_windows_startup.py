"""Discovery must not allocate a console or change its command contract."""
import os
from types import SimpleNamespace

import pytest

from harness import lane_runtime_support as support


@pytest.mark.parametrize("platform,expected", [("nt", 0x08000000), ("posix", 0)])
@pytest.mark.parametrize("probe", ["npm", "python"])
def test_discovery_process_does_not_create_windows_console(monkeypatch, tmp_path, platform,
                                                          expected, probe):
    # npm resolves through the guarded lookup (npm.cmd on Windows); the stand-in
    # in the one PATH folder is what the probe must start.
    npm = tmp_path / "bin" / ("npm.cmd" if os.name == "nt" else "npm")
    npm.parent.mkdir()
    npm.write_text("exit 0" + chr(10), encoding="utf-8")
    npm.chmod(0o755)
    monkeypatch.setenv("PATH", str(npm.parent))
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
        assert os.path.normcase(command[0]) == os.path.normcase(
            os.path.join(os.path.realpath(npm.parent), npm.name))
        assert command[1:] == ["root", "-g"]
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
