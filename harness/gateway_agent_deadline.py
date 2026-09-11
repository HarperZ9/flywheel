"""One aggregate monotonic deadline over an owned operation process tree."""
import time


def wait_for_worker(worker, deadline, *, clock=time.monotonic):
    from .gateway_operation_process import WorkerOutcome
    while True:
        remaining = deadline - clock()
        outcome = worker.wait(max(0, min(1.0, remaining)))
        if outcome is not None and clock() <= deadline: return outcome
        if remaining <= 0 or clock() >= deadline:
            if not worker.signal_tree():
                worker.close()
                return WorkerOutcome("failed", {"reason": "OWNERSHIP_UNAVAILABLE"})
            # Completion observed by the owned stop wins its natural race.
            final = worker.wait(0)
            observed = getattr(worker, "terminal_observed_at", None)
            if (getattr(final, "state", None) in {"completed", "failed"}
                    and observed is not None and observed <= deadline): return final
            return WorkerOutcome("failed", {"reason": "OPERATION_DEADLINE_EXCEEDED"})
