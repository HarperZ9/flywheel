"""egress_bridge.py -- the Linux half of the route, and why it has to exist.

`--unshare-net` gives a bubblewrap run a network namespace of its own with
nothing in it but loopback. That is the confinement, and it is also why the
proxy on the host is unreachable: the two loopbacks are different interfaces
with the same address. A namespace cannot be handed a socket that already
crossed it.

A pathname unix socket does cross it. Abstract unix sockets are scoped to the
network namespace and pathname ones are scoped to the filesystem, and the
scratch directory is already bind-mounted writable into the run. So the host
listens on a socket in there, and this runs inside the namespace to give the
confined command the thing it knows how to talk to: a TCP proxy on
127.0.0.1.

This is the entry point of the sandboxed run rather than a service beside
it. It binds the port first, then spawns the real command as a child, then
exits with the child's status. Binding first is the part that matters. A
command started before the listener was up would race its own proxy, and the
first connection would fail for a reason nothing in the record explains.

The macOS side needs none of this. Seatbelt is a policy over the host's own
stack rather than a namespace, so the confined process reaches the host's
127.0.0.1 directly and the profile names the port.

Run by path, not imported: `--ro-bind / /` leaves the repository readable
inside the sandbox, so this file is reachable at the same path it has
outside. The import below reflects that.
"""
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import threading
from pathlib import Path

try:
    from .egress_relay import splice
except ImportError:  # run by path inside a sandbox, not imported as a module
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from harness.egress_relay import splice

#: The exit code for a bridge that could not listen. The command does not
#: run. A run whose proxy never came up would fail somewhere inside whatever
#: the command was doing, and the record would blame the command.
BIND_FAILED = 126

#: How long the accept loop waits before checking whether the child is gone.
ACCEPT_POLL = 0.5


def _unix_upstream(socket_path: str):
    """A connection to the host's proxy, across the namespace boundary."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_path)
    return sock


def _serve(listener, stop: threading.Event, connect) -> None:
    """Carry each accepted connection to the host, one thread apiece.

    A client whose upstream cannot be reached is closed rather than left
    waiting. The proxy on the other end is what refuses a host, and a
    connection that never gets there is a broken route instead of a denied
    request. Those are different failures and this one belongs to the run.
    """
    listener.settimeout(ACCEPT_POLL)
    while not stop.is_set():
        try:
            conn, _ = listener.accept()
        except (socket.timeout, TimeoutError):
            continue
        except OSError:
            return
        threading.Thread(target=_carry, args=(conn, connect),
                         daemon=True).start()


def _carry(conn, connect) -> None:
    upstream = None
    try:
        upstream = connect()
        splice(conn, upstream)
    except OSError:
        pass
    finally:
        for sock in (conn, upstream):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass


def bridge(socket_path: str, port: int, argv: list, *,
           connect=None, spawn=None) -> int:
    """Listen, run `argv`, and exit with what it exited with.

    `connect` and `spawn` are injectable so the whole shape can be exercised
    on a host with no unix sockets and no bubblewrap: the ordering, the
    relay, and the exit code are the parts that can be wrong, and none of
    them is Linux-specific.
    """
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind(("127.0.0.1", port))
        listener.listen(16)
    except OSError as exc:
        listener.close()
        print(f"[egress bridge could not listen on {port}] "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return BIND_FAILED
    dial = connect if connect is not None else (
        lambda: _unix_upstream(socket_path))
    stop = threading.Event()
    worker = threading.Thread(target=_serve, args=(listener, stop, dial),
                              daemon=True)
    worker.start()
    try:
        run = spawn if spawn is not None else _spawn
        return run(argv)
    finally:
        stop.set()
        worker.join(timeout=2.0)
        listener.close()


def _spawn(argv: list) -> int:
    """The confined command, sharing this process's stdio."""
    return subprocess.run(argv).returncode


def main(args: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Give a network-namespaced command one TCP proxy.")
    parser.add_argument("--socket", required=True,
                        help="unix socket the host's proxy is listening on")
    parser.add_argument("--port", type=int, required=True,
                        help="loopback port to offer inside the namespace")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="-- followed by the command to run")
    parsed = parser.parse_args(args)
    command = parsed.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("no command given after --")
    return bridge(parsed.socket, parsed.port, command)


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    raise SystemExit(main())
