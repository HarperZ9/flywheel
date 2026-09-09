# ServiceDesk Incident Environment

Independent synthetic ServiceDesk incident environment product for agent evaluation.

This package exposes environment id `service-desk-incident/v1` through the dedicated `service-desk-incident-env` CLI and the `service_desk_incident_env` Python API. It depends on the first Flywheel engine release that contains `harness.enterprise_envs`: `flywheel-verify>=0.6.1,<0.7`.

The environment is synthetic and ServiceNow-like. It does not call ServiceNow, StateMachines, model providers, or external endpoints.
