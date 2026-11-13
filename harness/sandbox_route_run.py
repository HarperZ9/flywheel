"""sandbox_route_run.py -- one POSIX sandbox run, with or without an egress route.

Split out of `sandboxed_runner` so that file and its functions stay under the
size gates. The behaviour is unchanged.

Network is left reachable unless an operator named the hosts a run may reach.
The Windows backend cannot restrict it, so denying it here by default would
make one command succeed on one machine and fail on another for a reason no
caller asked about. `Confinement.network` records what held.

With `FLYWHEEL_EGRESS_HOSTS` set the run gets a proxy instead, the network is
denied around it, and every request the run made is in the output whether it
was carried or refused. A policy that was asked for and cannot be routed stops
the run. Falling back to the open network there would be the one moment the
feature was wanted and the one moment it did nothing.
"""
from __future__ import annotations


def routed_run(cmd: str, source, work, env: dict, timeout_seconds: int,
               runner=None, workspace=None):
    """Run `cmd` confined. Returns (rc, output, plan, attempts), or a refusal line.

    Raises SandboxUnavailable when the host has no backend that starts. A run
    that never started gets no confinement line from the caller: the summary
    states what the kernel enforced, and a failed exec enforced nothing.
    """
    from .egress_policy import PolicyRefused, from_env
    from .egress_route import RouteUnavailable, open_route
    from .posix_sandbox import backend_for, posix_run
    from .sandboxed_runner import SandboxUnavailable, _no_backend_reason
    try:
        policy = from_env()
    except PolicyRefused as exc:
        return f"[denied] egress policy is unreadable: {exc}"
    route, attempts = None, []
    try:
        if policy is not None:
            backend = backend_for()
            if backend is None:
                raise SandboxUnavailable(_no_backend_reason())
            route = open_route(policy, backend, work)
        outcome = posix_run(cmd, source, work, env=env, timeout_seconds=timeout_seconds,
                            network=policy is None,
                            egress=None if route is None else route.route, runner=runner,
                            **({} if workspace is None else workspace.posix()))
        if outcome is None:
            raise SandboxUnavailable(_no_backend_reason())
        if route is not None:
            attempts = route.record()["attempts"]
    except RouteUnavailable as exc:
        return f"[denied] no egress route for this run: {exc}"
    finally:
        if route is not None:
            route.close()
    return (*outcome, attempts)
