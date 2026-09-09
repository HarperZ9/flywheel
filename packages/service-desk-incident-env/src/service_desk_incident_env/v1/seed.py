"""Deterministic seed state for service-desk-incident/v1."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from harness.enterprise_envs.digest import digest

ENVIRONMENT_ID = "service-desk-incident/v1"

SEED_TABLES: dict[str, list[dict[str, Any]]] = {
    "cmdb_ci": [
        {"sys_id": "ci_vpn_gateway_01", "name": "vpn-gateway-01"},
        {"sys_id": "ci_payroll_app_01", "name": "payroll-app-01"},
    ],
    "incident": [
        {
            "sys_id": "inc_payroll_vpn",
            "number": "INC0010001",
            "short_description": "Payroll users cannot reach VPN",
            "assignment_group": "Help Desk",
            "priority": "4",
            "state": "New",
            "cmdb_ci": "",
            "work_notes": [],
        },
        {
            "sys_id": "inc_printer_floor3",
            "number": "INC0010002",
            "short_description": "Printer offline on floor 3",
            "assignment_group": "Help Desk",
            "priority": "4",
            "state": "New",
            "cmdb_ci": "",
            "work_notes": [],
        },
    ],
    "sys_attachment": [],
    "sys_audit": [],
}


def seed_tables() -> dict[str, list[dict[str, Any]]]:
    return deepcopy(SEED_TABLES)


def seed_sha256() -> str:
    return digest("flywheel.enterprise-env.seed/v1", {"environment_id": ENVIRONMENT_ID, "tables": SEED_TABLES})
