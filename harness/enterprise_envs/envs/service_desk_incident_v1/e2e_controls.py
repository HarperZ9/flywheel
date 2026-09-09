"""Compatibility shim for service_desk_incident_env.v1.e2e_controls."""
from harness.enterprise_envs.compat import export_service_desk_module as _export

_export(globals(), "e2e_controls")
