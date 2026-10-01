"""Native window-close check inside an owned Job, with isolated local settings."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import time

from desktop.tool import native_close_acceptance as native
from desktop.tool.installed_launch_acceptance_jobs import start_windows_job_process, WAIT_OBJECT_0


def profile_env(root):
    windows = os.environ.get('SYSTEMROOT', 'C:/Windows')
    env = {'SYSTEMROOT': windows, 'WINDIR': windows,
           'PATH': str(Path(windows) / 'System32')}
    for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'FLYWHEEL_HOME', 'TEMP', 'TMP'):
        folder = root / key.lower()
        folder.mkdir(parents=True, exist_ok=True)
        env[key] = str(folder)
    env.update({f'FLYWHEEL_LOCAL_AGENT_ALLOW_{grant}': '0' for grant in ('WRITE', 'EXEC', 'ONLINE')})
    env.update(FLYWHEEL_GIT='none', FLYWHEEL_BULLETIN_URL='http://127.0.0.1:1',
               HTTP_PROXY='http://127.0.0.1:1', HTTPS_PROXY='http://127.0.0.1:1',
               ALL_PROXY='http://127.0.0.1:1', NO_PROXY='127.0.0.1,localhost')
    return env


def post_close(hwnd):
    from ctypes import wintypes
    post = ctypes.windll.user32.PostMessageW
    post.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    post.restype = wintypes.BOOL
    return bool(post(hwnd, native.WM_CLOSE, 0, 0))


def wait_empty(job, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pids, error = job.active_pids()
        if error:
            return False
        if not pids:
            return True
        time.sleep(0.1)
    return False


def clean_exit(job):
    from ctypes import wintypes
    code = wintypes.DWORD()
    read = job.kernel.GetExitCodeProcess
    read.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    read.restype = wintypes.BOOL
    return bool(read(job.process.hProcess, ctypes.byref(code))) and code.value == 0


def run(install_root, work):
    receipt = {'verdict': 'HOLD', 'stage': 'port_preflight', 'owned_job_empty': False}
    job = None
    try:
        if native._port_listener_rows(8799):
            return receipt
        work.mkdir(parents=True, exist_ok=False)
        env = profile_env(work)
        receipt['stage'] = 'launch'
        job, error = start_windows_job_process(install_root / 'flywheel_desktop.exe', [], env,
            install_root, work / 'stdout.log', work / 'stderr.log', show_window=True)
        if error or job is None:
            return receipt
        receipt['stage'] = 'window'
        hwnd = native._wait_for_window(job.pid, 20)
        if not hwnd:
            return receipt
        receipt['window_observed'] = True
        receipt['stage'] = 'owned_gateway'
        gateways, _ = native._wait_for_owned_gateway(job.pid,
            install_root / 'engine/flywheel-gateway.exe', 30)
        if not gateways:
            return receipt
        receipt['owned_gateway_observed'] = True
        receipt['stage'] = 'close'
        if not post_close(hwnd):
            return receipt
        if job.kernel.WaitForSingleObject(job.process.hProcess, 20000) != WAIT_OBJECT_0:
            return receipt
        if not clean_exit(job):
            return receipt
        receipt['stage'] = 'owned_cleanup'
        if not wait_empty(job, 10):
            return receipt
        if not job.close():
            return receipt
        job = None
        receipt.update(verdict='PASS', stage='complete', owned_job_empty=True)
    except Exception:
        receipt['failure'] = 'NATIVE_UI_CHECK_FAILED'
    finally:
        if job is not None:
            try:
                cleanup = job.terminate_and_verify(timeout_ms=5000)
                receipt['forced_cleanup'] = cleanup.get('state')
            except Exception:
                job.close()  # Kill-on-close still bounds the owned tree if verification failed.
                receipt['forced_cleanup'] = 'FAIL'
            # Forced termination is cleanup, never successful native close evidence.
            receipt['verdict'] = 'HOLD'
    return receipt
