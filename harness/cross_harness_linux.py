"""Private cgroup-v2 containment for Linux provider processes."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
import uuid

MAX_CAPTURE_BYTES = 1 << 20


def _current_cgroup_root() -> Path:
    try:
        rows = Path("/proc/self/cgroup").read_text(encoding="utf-8").splitlines()
        relative = next(row.split("::", 1)[1] for row in rows if row.startswith("0::"))
    except (OSError, StopIteration, IndexError) as exc:
        raise OSError("unified cgroup v2 membership unavailable") from exc
    return Path("/sys/fs/cgroup") / relative.lstrip("/")


class LinuxCgroup:
    def __init__(self, path: Path):
        self.path = path

    def wrap(self, argv: list[str]) -> list[str]:
        payload = base64.urlsafe_b64encode(json.dumps(argv).encode("utf-8")).decode("ascii")
        return [sys.executable, "-I", str(Path(__file__).resolve()), "--exec", str(self.path), payload]

    def kill_and_remove(self, timeout: float = .75) -> None:
        failure = None
        try:
            (self.path / "cgroup.kill").write_text("1", encoding="ascii")
        except OSError as exc:
            failure = exc
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if "populated 0" in (self.path / "cgroup.events").read_text(encoding="ascii"):
                    break
            except OSError as exc:
                failure = failure or exc
                break
            time.sleep(.01)
        else:
            failure = failure or OSError("provider cgroup remained populated")
        try:
            self.path.rmdir()
        except OSError as exc:
            failure = failure or exc
        if failure:
            raise OSError("provider cgroup teardown failed") from failure


def prepare_linux_cgroup() -> LinuxCgroup:
    parent = _current_cgroup_root()
    if not (parent / "cgroup.controllers").is_file():
        raise OSError("private cgroup v2 containment unavailable")
    path = parent / f"flywheel-provider-{os.getpid()}-{uuid.uuid4().hex}"
    try:
        path.mkdir(mode=0o700)
        for name in ("cgroup.procs", "cgroup.kill", "cgroup.events"):
            if not (path / name).is_file():
                raise OSError(f"cgroup v2 control missing: {name}")
        with (path / "cgroup.procs").open("a", encoding="ascii"):
            pass
        (path / "cgroup.kill").write_text("1", encoding="ascii")
    except OSError as exc:
        try:
            path.rmdir()
        except OSError:
            pass
        raise OSError("private cgroup v2 containment unavailable") from exc
    return LinuxCgroup(path)


def _close(selector: selectors.BaseSelector, stream) -> None:
    try:
        selector.unregister(stream)
    except (KeyError, ValueError):
        pass
    try:
        stream.close()
    except OSError:
        pass


def run_linux_process(proc: subprocess.Popen, group: LinuxCgroup, stdin: bytes,
                      deadline: float) -> tuple[dict[str, tuple[bytes, bool]], bool]:
    selector = None
    captured = {"stdout": [bytearray(), False], "stderr": [bytearray(), False]}
    streams = (proc.stdout, proc.stderr, proc.stdin)
    pending = memoryview(stdin)

    def pump(wait: float) -> None:
        nonlocal pending
        for key, _ in selector.select(wait):
            stream, name = key.fileobj, key.data
            if name == "stdin":
                try:
                    count = os.write(stream.fileno(), pending[:65536])
                    pending = pending[count:]
                except (BlockingIOError, BrokenPipeError, OSError):
                    pending = memoryview(b"")
                if not pending:
                    _close(selector, stream)
                continue
            try:
                chunk = os.read(stream.fileno(), 65536)
            except BlockingIOError:
                continue
            except OSError:
                chunk = b""
                captured[name][1] = True
            if not chunk:
                _close(selector, stream)
                continue
            data, overflow = captured[name]
            room = max(0, MAX_CAPTURE_BYTES - len(data))
            data.extend(chunk[:room])
            captured[name][1] = overflow or len(chunk) > room

    try:
        selector = selectors.DefaultSelector()
        for stream, key in ((proc.stdout, "stdout"), (proc.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False); selector.register(stream, selectors.EVENT_READ, key)
        os.set_blocking(proc.stdin.fileno(), False)
        if pending: selector.register(proc.stdin, selectors.EVENT_WRITE, "stdin")
        else: proc.stdin.close()
        while proc.poll() is None and time.monotonic() < deadline:
            pump(min(.05, max(0, deadline - time.monotonic())))
        timed_out = proc.poll() is None
    finally:
        teardown = None
        try: group.kill_and_remove()
        except OSError as exc: teardown = exc
        if proc.poll() is None:
            proc.kill()
        try: proc.wait(timeout=.5)
        except (AttributeError, subprocess.TimeoutExpired) as exc: teardown = teardown or exc
        if selector:
            for stream in streams: _close(selector, stream)
            selector.close()
        else:
            for stream in streams:
                try: stream.close()
                except OSError: pass
        if teardown: raise OSError("Linux provider cleanup failed") from teardown
    return {key: (bytes(value[0]), bool(value[1])) for key, value in captured.items()}, timed_out


def _exec_in_cgroup(group: Path, payload: str) -> None:
    argv = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        raise OSError("invalid provider argv envelope")
    (group / "cgroup.procs").write_text(str(os.getpid()), encoding="ascii")
    members = {int(item) for item in (group / "cgroup.procs").read_text().split()}
    if os.getpid() not in members:
        raise OSError("provider bootstrap did not enter private cgroup")
    os.execvpe(argv[0], argv, os.environ)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--exec":
        raise SystemExit(125)
    try:
        _exec_in_cgroup(Path(sys.argv[2]), sys.argv[3])
    except Exception:
        raise SystemExit(125)
