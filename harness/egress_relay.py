"""egress_relay.py -- carrying bytes, and letting go of a socket politely.

Nothing here reads what passes or decides anything. The allowlist lives in
`egress_policy` and the decision in `egress_proxy`. This is the plumbing
both of them stand on, and it is its own module because a tunnel that
inspected its own traffic would be a second thing to be wrong about, on
exactly the traffic the policy already permitted.

`egress_bridge` imports `splice` from here and runs inside a network
namespace with nothing else from the package reachable, which is the other
reason the plumbing is separable from the policy.
"""
from __future__ import annotations

import selectors
import socket
import threading

#: How often an open tunnel wakes to check whether either side has gone. A
#: tunnel with no traffic is the normal state of a long download, so this
#: is a liveness check and not a deadline.
SPLICE_POLL = 30.0

#: How long a refused connection waits for the client to stop talking. Long
#: enough for a client that is mid-send, short enough that a client which
#: never stops cannot keep the thread.
DRAIN_TIMEOUT = 2.0

#: The most a refused connection reads while draining. A client sending
#: more than this after a refusal is not going to be talked round.
MAX_DRAIN = 32768

#: How often the accept loop wakes to check whether it was asked to stop.
ACCEPT_POLL = 0.5


def quiet(call, *args) -> None:
    """Call it, and let a dead socket be dead."""
    try:
        call(*args)
    except OSError:
        pass


def farewell(conn) -> None:
    """Close in a way that lets a refusal already written actually arrive.

    Closing a socket with bytes still queued on the receive side sends a
    reset, and a reset throws away whatever this end had written but not
    yet delivered. A refused client is usually still sending when that
    happens, so the message naming the refusal is the thing discarded, and
    the client reports a dropped connection rather than the reason.

    Half-closing says there is nothing more to write. The drain empties the
    queue so the close after it is an ordinary one. Both halves are
    bounded, because being refused must not be a way to hold this thread.
    """
    quiet(conn.shutdown, socket.SHUT_WR)
    quiet(conn.settimeout, DRAIN_TIMEOUT)
    dropped = 0
    try:
        while dropped < MAX_DRAIN:
            chunk = conn.recv(65536)
            if not chunk:
                return
            dropped += len(chunk)
    except OSError:
        return


def splice(left, right) -> None:
    """Carry bytes both ways until one side is done.

    Nothing here reads what passes. The policy decided the destination and
    the tunnel is a tunnel.
    """
    selector = selectors.DefaultSelector()
    selector.register(left, selectors.EVENT_READ, right)
    selector.register(right, selectors.EVENT_READ, left)
    try:
        while True:
            for key, _ in selector.select(timeout=SPLICE_POLL):
                data = key.fileobj.recv(65536)
                if not data:
                    return
                key.data.sendall(data)
    except OSError:
        return
    finally:
        selector.close()


def serve(proxy, listener, stop: threading.Event) -> None:
    """Accept until `stop` is set. One thread per connection.

    The listener carries the timeout, so a run whose command exits without
    closing a connection still lets this loop notice `stop` and return.
    """
    listener.settimeout(ACCEPT_POLL)
    workers: list = []
    while not stop.is_set():
        try:
            conn, _ = listener.accept()
        except (socket.timeout, TimeoutError):
            continue
        except OSError:
            break
        worker = threading.Thread(target=proxy.handle, args=(conn,),
                                  daemon=True)
        worker.start()
        workers.append(worker)
    for worker in workers:
        worker.join(timeout=1.0)
