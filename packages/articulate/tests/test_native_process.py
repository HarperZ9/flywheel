"""A hung native probe must not leave its spawned child behind."""
import ctypes
import os
from pathlib import Path
import sys
import time

import pytest

from claude_plugin_helpers import load

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows job boundary')


def environment():
    return {k: v for k, v in os.environ.items()
            if k.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}


def test_timeout_kills_a_real_spawned_child(tmp_path):
    script = tmp_path / 'parent.py'
    pidfile = tmp_path / 'child.pid'
    script.write_text('import pathlib,subprocess,sys,time\n'
                      'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"])\n'
                      'pathlib.Path(sys.argv[1]).write_text(str(p.pid))\n'
                      'time.sleep(60)\n')
    # The timeout must outlast a slow interpreter start on a loaded machine, so
    # the child exists before the kill. The bound still sits far below the
    # 60 s sleep, so a runner that waits for the child fails it.
    timeout = 8
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        load('native_windows_process').run_process(sys.executable, [str(script), str(pidfile)],
                                                   environment(), tmp_path, '', timeout=timeout)
    assert time.monotonic() - start < timeout + 20
    assert pidfile.exists(), 'child must have started before timeout'
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x100000, False, int(pidfile.read_text()))
    if handle:
        try:
            # The job kill is asynchronous; give the child up to 10 s to exit,
            # far below its 60 s sleep.
            assert kernel.WaitForSingleObject(handle, 10_000) == 0
        finally:
            kernel.CloseHandle(handle)


def test_runner_captures_stdout_stderr_and_exit(tmp_path):
    result = load('native_windows_process').run_process(sys.executable,
        ['-c', 'import sys; print(sys.stdin.read()); print("denied",file=sys.stderr); sys.exit(2)'],
        environment(), tmp_path, 'input', timeout=30)
    assert result == (2, 'input\n', 'denied\n')
