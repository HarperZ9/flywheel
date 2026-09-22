"""Last-moment policy check for an owned, still-suspended provider child."""
from __future__ import annotations


def verify_before_resume(owned, check) -> None:
    """A check succeeds only by returning None; rejection never resumes a child.

    The sanitized exception retains process custody for the launcher if cleanup
    is incomplete. A caller must keep its policy lease until that cleanup passes.
    """
    if check is None:
        return
    from .provider_session_process import ProviderSessionProcessError
    try:
        if check() is None:
            return
    except Exception:
        pass
    cleanup = owned.close()
    if cleanup.exited and cleanup.stderr_drain_complete:
        # No transport has received these pipes yet. Close them only after the
        # child has exited, so cleanup cannot block behind a suspended reader.
        for stream in (owned.stdin, owned.stdout):
            try:
                stream.close()
            except Exception:
                pass
    error = ProviderSessionProcessError('provider session prelaunch check failed')
    error.owned_process = owned
    raise error from None
