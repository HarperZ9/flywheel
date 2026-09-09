"""Compatibility shim for service_desk_incident_env.v1.oracle."""
from harness.enterprise_envs.compat import export_service_desk_module as _export

_export(globals(), "oracle")
