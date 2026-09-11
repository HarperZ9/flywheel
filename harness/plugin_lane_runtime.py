"""Public plugin projections and fixed failures for unavailable lane runtimes."""
from .gateway_operation import GatewayOperationError
from .lane_runtime import LaneRuntimeError


def unavailable_response(name: str) -> dict:
    return {"name": name, "kind": "lane", "status": "unavailable",
            "code": "LANE_UNAVAILABLE", "error": "lane runtime is unavailable; inspect Lanes for details"}


def require_lane_launch(name, resolver):
    try:
        return resolver(name)
    except LaneRuntimeError:
        raise GatewayOperationError("LANE_UNAVAILABLE") from None


def lane_plugin_row(name, lane, command_resolver, runtime_resolver):
    runtime = runtime_resolver(name)
    row = {"name": name, "kind": "lane", "enabled": runtime.present,
           "removable": False, "detail": lane.role, "organ": lane.organ,
           "command": [], "status": (f"{runtime.selected_runtime}_selected"
                                      if runtime.present else "unavailable"),
           "resolved_runtime": runtime.to_dict()}
    if lane.package_disabled_reason and not runtime.present:
        row['detail'] = f"{lane.role}. {lane.package_disabled_reason}"
    return row
