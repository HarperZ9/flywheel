"""Machine-readable discovery: what this gateway serves, in three shapes.

An agent that lands on a workstation has no way to learn what it can ask for.
It guesses paths, or a human pastes a list into its prompt, and both go stale.
Three documents answer that. They start with `route_inventory`, which reads the
gateway's own dispatchers, and OpenAPI also includes descriptor-backed typed
Writing operation paths from `writing_operations`:

    GET /openapi.json           OpenAPI 3.1, for a client that generates calls
    GET /llms.txt               the llmstxt.org shape, for a model reading prose
    GET /.well-known/flywheel.json   a small card pointing at the other two

The route inventory is still a lower bound: a path assembled at runtime is
invisible to the dispatcher parse. The typed Writing additions are bounded to
that operation family and are guarded against adapter drift in tests.

Two deliberate limits. The documents ride the same authentication as every
other route, so a gateway with a token configured does not answer them to a
stranger; this is an index for a caller that already has access, not an
advertisement. And `/.well-known/flywheel.json` is vendor-namespaced. It is
not an IANA-registered well-known URI and does not implement anyone else's
agent-card specification.
"""

from __future__ import annotations

import importlib.metadata as metadata
import json
from typing import Any

from harness.gateway_custody import is_private
from harness.route_inventory import PREFIX, Route, gateway_routes
from harness.writing_operations import http_operations, openapi_path_items

SCHEMA = "flywheel.discovery/v1"
OPENAPI_PATH = "/openapi.json"
LLMS_PATH = "/llms.txt"
CARD_PATH = "/.well-known/flywheel.json"
PATHS = (OPENAPI_PATH, LLMS_PATH, CARD_PATH)


def installed_version() -> str:
    """The version the documents report, resolved rather than typed.

    A version repeated in a generated document is one more thing that goes
    stale on a release, so it is read from the installed distribution and
    falls back to a word that cannot be mistaken for a release.
    """
    try:
        return metadata.version("flywheel-verify")
    except metadata.PackageNotFoundError:
        return "unknown"


#: Said in each document, because a reader who takes the inventory for a
#: complete list will conclude a missing route does not exist.
LOWER_BOUND = (
    "Generated from parsed gateway dispatchers plus descriptor-backed Writing "
    "operation paths. Runtime-assembled paths do not appear here, so treat the "
    "inventory as a lower bound on what is served. Descriptor-backed paths are "
    "bounded to Writing operations and are guarded against adapter drift."
)

#: Path prefix to section heading, longest prefix winning. Only used to group
#: the routes for a reader; nothing depends on a route landing in one group.
GROUPS = (
    ("/api/governance", "Governance and tiers"),
    ("/api/infra", "Infrastructure controls"),
    ("/api/relay", "Mobile and desktop relay"),
    ("/api/forum", "Forum and gates"),
    ("/api/agent", "Agent runs"),
    ("/api/operations", "Long-running operations"),
    ("/api/journeys", "Journeys"),
    ("/v1/", "OpenAI-compatible"),
    ("/api/", "Engine"),
)


def _group(path: str) -> str:
    for prefix, title in GROUPS:
        if path.startswith(prefix):
            return title
    return "Service"


def _operation(route: Route, method: str) -> dict[str, Any]:
    op: dict[str, Any] = {
        "summary": route.description or f"{method} {route.path}",
        "operationId": f"{method.lower()}{route.path.replace('/', '_')}",
        "tags": [_group(route.path)],
        "responses": {"200": {"description": "the handler's JSON reply"}},
    }
    if not route.description:
        op["x-flywheel-undescribed"] = True
    if is_private(route.path):
        op["security"] = [{"bearerAuth": []}]
        op["x-flywheel-custody"] = "private"
    return op


def _descriptor_paths() -> set[str]:
    return {op.http_path for op in http_operations()}


def _openapi_path_count(routes: list[Route]) -> int:
    parsed = {r.path + "{subpath}" if r.match == PREFIX else r.path
              for r in routes}
    return len(parsed | _descriptor_paths())


def openapi_document(version: str = "") -> dict[str, Any]:
    """The route inventory as OpenAPI 3.1.

    A prefix route is written with a trailing `{subpath}` parameter, which is
    the closest OpenAPI shape to "everything under here" and is marked with
    `x-flywheel-match` so a reader is not left inferring it from the brace.
    """
    version = version or installed_version()
    paths: dict[str, Any] = {}
    routes = gateway_routes()
    for route in routes:
        key = route.path + "{subpath}" if route.match == PREFIX else route.path
        entry: dict[str, Any] = {
            m.lower(): _operation(route, m) for m in route.methods}
        entry["x-flywheel-match"] = route.match
        if route.match == PREFIX:
            entry["parameters"] = [{
                "name": "subpath", "in": "path", "required": True,
                "description": "the rest of the path after the prefix",
                "schema": {"type": "string"}}]
        paths[key] = entry
    paths.update(openapi_path_items(_group))
    return {
        "openapi": "3.1.0",
        "info": {"title": "Flywheel gateway", "version": version,
                 "description": LOWER_BOUND},
        "components": {"securitySchemes": {"bearerAuth": {
            "type": "http", "scheme": "bearer"}}},
        "x-flywheel-route-sources": {
            "dispatcher_paths": len(routes),
            "descriptor_backed_paths": len(_descriptor_paths())},
        "x-flywheel-typed-route-scope": ["writing operations"],
        "paths": paths,
    }


def _llms_sections(routes: list[Route]) -> list[str]:
    sections: dict[str, list[str]] = {}
    for route in routes:
        note = route.description or "no description on the dispatch line"
        custody = " (private custody, bearer token required)" if is_private(
            route.path) else ""
        sections.setdefault(_group(route.path), []).append(
            f"- [{'|'.join(route.methods)} {route.path}]({route.path}): "
            f"{note}{custody}")
    for op in http_operations():
        sections.setdefault(_group(op.http_path), []).append(
            f"- [{op.http_method} {op.http_path}]({op.http_path}): "
            f"{op.description} (descriptor-backed Writing operation; "
            "private custody, bearer token required)")
    out = []
    for _, title in GROUPS + (("", "Service"),):
        lines = sections.pop(title, None)
        if lines:
            out.append(f"## {title}\n\n" + "\n".join(sorted(lines)))
    return out


def llms_txt(version: str = "") -> str:
    """The same inventory in the llmstxt.org shape: H1, summary, link lists.

    A model reading this gets the paths and the one-line descriptions their
    authors wrote beside the dispatch, which is the part a generated OpenAPI
    document buries under structure.
    """
    version = version or installed_version()
    routes = gateway_routes()
    head = (f"# Flywheel gateway {version}\n\n"
            f"> The local verification engine's HTTP surface: {len(routes)} "
            f"dispatcher paths plus {len(_descriptor_paths())} "
            "descriptor-backed Writing operation paths. Replies are JSON.\n\n"
            f"{LOWER_BOUND}\n")
    return head + "\n\n" + "\n\n".join(_llms_sections(routes)) + "\n"


def card(version: str = "") -> dict[str, Any]:
    """The small document that points at the other two."""
    version = version or installed_version()
    routes = gateway_routes()
    return {
        "schema": SCHEMA,
        "service": "flywheel-verify",
        "version": version,
        "routes": _openapi_path_count(routes),
        "dispatcher_routes": len(routes),
        "descriptor_backed_routes": len(_descriptor_paths()),
        "typed_route_scope": ["writing operations"],
        "undescribed": sum(1 for r in routes if not r.description),
        "discovery": {"openapi": OPENAPI_PATH, "llms_txt": LLMS_PATH},
        "authentication": {
            "scheme": "bearer",
            "note": ("Required on every route when the gateway is started "
                     "with a token, and always required on the routes marked "
                     "private custody."),
        },
        "note": LOWER_BOUND,
    }


def handle_discovery_get(path: str, *, version: str = ""
                         ) -> tuple[bytes, str, int] | None:
    """Serve one discovery document, or `None` when the path is not ours.

    Returns the body already encoded with its content type, because `llms.txt`
    is text and the other two are JSON, and a caller that has to remember
    which is which will eventually send the wrong header.
    """
    if path == LLMS_PATH:
        return (llms_txt(version).encode("utf-8"),
                "text/plain; charset=utf-8", 200)
    if path == OPENAPI_PATH:
        doc: Any = openapi_document(version)
    elif path == CARD_PATH:
        doc = card(version)
    else:
        return None
    return (json.dumps(doc, indent=2, sort_keys=True).encode("utf-8"),
            "application/json", 200)
