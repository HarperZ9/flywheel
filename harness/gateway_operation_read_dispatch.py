"""Read selectors for existing supervised operations and Journey discovery."""
from urllib.parse import parse_qs
from .gateway_operation import GatewayOperationError

def _read(method: str, path: str, query: str, owner_ref: str,
          service):
    from .gateway_operation_route import RouteResponse, _OPERATION_PATH, _stream
    if method == "GET" and path == "/api/operations":
        from .gateway_operation_discovery import list_operations
        return RouteResponse(200, list_operations(service, owner_ref, query))
    match = _OPERATION_PATH.fullmatch(path)
    if method != "GET" or match is None:
        raise GatewayOperationError("INVALID_REQUEST")
    ref, selector = match.groups()
    if selector == "trace":
        from .gateway_agent_trace_route import read_trace; return RouteResponse(200, read_trace(service, owner_ref, ref, query))
    if selector == "events":
        values = parse_qs(query, keep_blank_values=True, strict_parsing=True)
        if set(values) - {"after"} or any(len(value) != 1 for value in values.values()):
            raise GatewayOperationError("INVALID_REQUEST")
        raw_after = values.get("after", ["0"])[0]
        if (len(raw_after) > 18 or not raw_after.isascii()
                or not raw_after.isdecimal()):
            raise GatewayOperationError("INVALID_REQUEST")
        return RouteResponse(200, stream=_stream(
            service, owner_ref, ref, after=int(raw_after)))
    if query: raise GatewayOperationError("INVALID_REQUEST")
    value = service.result(owner_ref, ref) if selector == "result" else (
        service.snapshot(owner_ref, ref).as_json())
    return RouteResponse(200, value)
