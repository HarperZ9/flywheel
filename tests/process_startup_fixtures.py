"""Test-only startup barriers for process cleanup controls."""
import time


class ReadyOwnedProcess:
    """Resume the real owned process, then establish the cleanup precondition.

    The supervisor computes its wait budget before resume(), so this fixture
    separates bounded interpreter startup from the unchanged timeout/kill wait.
    All process operations and outcomes remain those of the real owned process.
    """
    def __init__(self, owned, marker, read_text, is_running, *, startup_timeout=30):
        self._owned = owned
        self.marker, self.read_text, self.is_running = marker, read_text, is_running
        self.startup_timeout = startup_timeout
        self.pid = self.ready_at = None

    def __getattr__(self, name):
        return getattr(self._owned, name)

    def resume(self):
        if not self._owned.resume():
            return False
        value = self.read_text(self.marker, timeout=self.startup_timeout,
                               why="recorder did not publish its descendant pid")
        pid = int(value.strip())
        assert pid > 0 and self.is_running(pid), "descendant was not alive before timeout"
        self.pid, self.ready_at = pid, time.monotonic()
        return True


def windows_pid_is_running(pid):
    """Preserve the cleanup test's native query, including query failures."""
    import ctypes
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.restype = ctypes.c_void_p
    api.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    api.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    api.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = api.OpenProcess(0x1000, 0, pid)
    if not handle:
        return False
    code = ctypes.c_uint32()
    try:
        assert api.GetExitCodeProcess(handle, ctypes.byref(code)), "process state query failed"
        return code.value == 259
    finally:
        api.CloseHandle(handle)
