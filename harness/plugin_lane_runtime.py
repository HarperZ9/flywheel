"""Public plugin projections and fixed failures for unavailable lane runtimes."""
from .gateway_operation import GatewayOperationError
from .lane_runtime import LaneRuntimeError


def unavailable_response(name: str) -> dict:
    return {"name": name, "kind": "lane", "status": "unavailable",
            "code": "LANE_UNAVAILABLE", "error": "lane runtime is unavailable; inspect Lanes for details"}


def require_lane_launch(name, resolver):
    """The lane's launch, or a lane code from the closed set: LANE_SETUP_REQUIRED
    when only a setup step blocks it, LANE_CANNOT_LAUNCH otherwise (S7)."""
    try:
        return resolver(name)
    except LaneRuntimeError as error:
        from .lane_runtime_frozen import NEEDS_SETUP, launch_state
        setup = launch_state(error.codes) == NEEDS_SETUP
        raise GatewayOperationError(
            "LANE_SETUP_REQUIRED" if setup else "LANE_CANNOT_LAUNCH") from None


def lane_plugin_row(name, lane, command_resolver, runtime_resolver):
    row = {"name": name, "kind": "lane", "enabled": True, "removable": False,
           "detail": lane.role, "organ": lane.organ, "command": command_resolver(name)}
    if lane.package_disabled_reason:
        runtime = runtime_resolver(name)
        row.update(enabled=runtime.present, command=[],
                   status=(f"{runtime.selected_runtime}_selected"
                           if runtime.present else "unavailable"),
                   detail=f"{lane.role}. {lane.package_disabled_reason}")
    return row
