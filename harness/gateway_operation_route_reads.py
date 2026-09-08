from __future__ import annotations

from collections.abc import Callable
from threading import Condition
from typing import TypeVar

from .gateway_operation import GatewayOperationError

T = TypeVar("T")


def read_after_store_busy(read: Callable[[], T], condition: Condition,
                          *, wait_s: float = 0.25) -> T:
    try:
        return read()
    except GatewayOperationError as exc:
        if exc.code != "STORE_BUSY":
            raise
        with condition:
            condition.wait(wait_s)
        return read()


def read_snapshot(service, owner_ref: str, operation_ref: str,
                  condition: Condition):
    return read_after_store_busy(
        lambda: service.snapshot(owner_ref, operation_ref), condition)


def read_snapshot_or_none(service, owner_ref: str, operation_ref: str,
                          condition: Condition):
    try:
        return read_snapshot(service, owner_ref, operation_ref, condition)
    except GatewayOperationError as exc:
        if exc.code != "STORE_BUSY":
            raise
        return None


def terminal_data(service, owner_ref: str, operation_ref: str,
                  condition: Condition) -> dict:
    snapshot = read_snapshot(service, owner_ref, operation_ref, condition)
    result = read_after_store_busy(
        lambda: service.result(owner_ref, operation_ref), condition)
    return {"snapshot": snapshot.as_json(), "result": result}
