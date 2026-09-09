"""Compatibility shim for service_desk_incident_env.v1.calibration_cases."""
from harness.enterprise_envs.compat import export_service_desk_module as _export

_export(globals(), "calibration_cases")
