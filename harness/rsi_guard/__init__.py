# SPDX-License-Identifier: MIT
"""Pure-stdlib OSI MIT RSI guard package (`STA-070`, `N49`, `N25`, `J13`, `N56`)."""

from __future__ import annotations

from .drift_monitor import (
    HONEST_SCOPE_LIMIT as DRIFT_MONITOR_LIMIT,
    DriftAlert,
    DriftMonitor,
    DriftPolicy,
    StepTelemetry,
    assess_series,
)
from .goodhart_valve import (
    HONEST_SCOPE_LIMIT as GOODHART_VALVE_LIMIT,
    CandidateStep,
    StepDecision,
    ValvePolicy,
    evaluate_rsi_step,
    simulate_arm_a_vs_arm_b,
)
from .receipt_bridge import (
    ENGINE_RECEIPT_SCHEMA,
    HONEST_SCOPE_LIMIT as RECEIPT_BRIDGE_LIMIT,
    LEDGER_ENTRY_SCHEMA,
    append_verified_receipt_to_ledger,
    compute_engine_receipt_digests,
    verify_engine_receipt,
    verify_receipt_ledger,
)

HONEST_SCOPE_LIMITS = {
    "goodhart_valve": GOODHART_VALVE_LIMIT,
    "drift_monitor": DRIFT_MONITOR_LIMIT,
    "receipt_bridge": RECEIPT_BRIDGE_LIMIT,
}

__all__ = [
    "ENGINE_RECEIPT_SCHEMA",
    "HONEST_SCOPE_LIMITS",
    "LEDGER_ENTRY_SCHEMA",
    "CandidateStep",
    "DriftAlert",
    "DriftMonitor",
    "DriftPolicy",
    "StepDecision",
    "StepTelemetry",
    "ValvePolicy",
    "append_verified_receipt_to_ledger",
    "assess_series",
    "compute_engine_receipt_digests",
    "evaluate_rsi_step",
    "simulate_arm_a_vs_arm_b",
    "verify_engine_receipt",
    "verify_receipt_ledger",
]
