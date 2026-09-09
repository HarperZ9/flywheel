"""Compatibility imports for optional enterprise environment products."""
from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any


class EnterpriseEnvironmentProductMissing(ImportError):
    def __init__(self, environment_id: str, distribution: str):
        self.environment_id = environment_id
        self.distribution = distribution
        self.error_code = "enterprise_environment_product_missing"
        super().__init__(f"{environment_id} requires installed product distribution {distribution}")


def load_service_desk_module(module_name: str) -> ModuleType:
    try:
        return importlib.import_module(f"service_desk_incident_env.v1.{module_name}")
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("service_desk_incident_env"):
            raise EnterpriseEnvironmentProductMissing("service-desk-incident/v1", "flywheel-env-service-desk-incident") from exc
        raise


def load_service_desk_product() -> ModuleType:
    try:
        return importlib.import_module("service_desk_incident_env.product")
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("service_desk_incident_env"):
            raise EnterpriseEnvironmentProductMissing("service-desk-incident/v1", "flywheel-env-service-desk-incident") from exc
        raise


def export_service_desk_module(namespace: dict[str, Any], module_name: str) -> None:
    module = load_service_desk_module(module_name)
    for name, value in module.__dict__.items():
        if not name.startswith("_"):
            namespace[name] = value
    namespace["__all__"] = [name for name in module.__dict__ if not name.startswith("_")]
