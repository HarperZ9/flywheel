"""Explicit opt-in registration; no browser discovery or launch at startup."""
import threading

from .browser_control import register_driver
from .telos_browser_adapter import TelosBrowserAdapter
from .telos_browser_config import load_config


_CONFIGURE_LOCK = threading.Lock()


def _remove(unregister) -> bool:
    try:
        if unregister is None:
            from .browser_control import unregister_driver
            unregister = unregister_driver
        unregister("telos-browser")
        return True
    except Exception:
        return False


def configure_telos_browser(config_path, *, register=register_driver, unregister=None) -> dict:
    unknown = {"available": None, "code": "registration_state_unknown", "driver": None}
    with _CONFIGURE_LOCK:
        if not _remove(unregister):
            return unknown
        if config_path is None:
            return {"available": False, "code": "not_configured", "driver": None}
        try:
            adapter = TelosBrowserAdapter(load_config(config_path))
            register(adapter.driver_name, adapter, binding_sha256=adapter.binding_sha256)
        except Exception:
            if not _remove(unregister):
                return unknown
            return {"available": False, "code": "configuration_unavailable", "driver": None}
        return {"available": True, "code": "configured_not_runtime_verified",
                "driver": adapter.driver_name, "binding_sha256": adapter.binding_sha256}
