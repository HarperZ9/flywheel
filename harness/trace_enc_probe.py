"""The start-up probe and the encryption status line (7.3, EN-B7, D7).

At start the gateway encrypts and decrypts a probe value. A failed probe
shows in status and in the doctor as `encryption: unavailable (<code>)`, and
per decision D7 writes to a store that already holds encrypted items fail
with ENC_REQUIRED while stores never encrypted stay plaintext, loudly.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from .trace_enc import EncError

_log = logging.getLogger(__name__)
PROBE = b"flywheel.encryption.probe.v1"


def probe(provider) -> dict:
    if provider.name == "none":
        return {"ok": False, "provider": "none", "code": "NO_OS_KEY_STORE"}
    try:
        key = os.urandom(32)
        ok = provider.decrypt(key, provider.encrypt(key, PROBE, b"probe"), b"probe") == PROBE
        sealed = provider.unseal(provider.seal(PROBE, b"probe"), b"probe") == PROBE
    except EncError as exc:
        return {"ok": False, "provider": provider.name, "code": exc.code}
    except OSError as exc:
        return {"ok": False, "provider": provider.name, "code": f"OS_ERROR:{exc.errno}"}
    return {"ok": bool(ok and sealed), "provider": provider.name,
            "code": None if ok and sealed else "PROBE_MISMATCH"}


def encryption_status(state_root) -> dict:
    """What `flywheel traces status` and the doctor print about encryption."""
    from .trace_enc import default_provider
    from .trace_enc_floor import floors
    provider = default_provider()
    status = provider.status()
    return {"provider": status["provider"], "protection": status["protection"],
            "floors": floors(state_root)}


def startup(home) -> dict:
    """Gateway start: probe the provider, label the custody tree once."""
    from .trace_fs_attrs import label_tree, set_not_indexed
    status = encryption_status(Path(home) / "state")
    try:
        label_tree(Path(home))
        for directory in (Path(home), Path(home) / "state"):
            if directory.is_dir():
                set_not_indexed(directory)
    except OSError as exc:
        _log.warning("custody tree attributes not applied (%s)", type(exc).__name__)
    if status["provider"] == "none":
        _log.warning("trace custody is %s", status["protection"])
    return status
