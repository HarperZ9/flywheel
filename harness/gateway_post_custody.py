"""Extracted custody, review, hooks, subagent, and grant-authorization POST helpers."""
from __future__ import annotations

import json
from pathlib import Path

_INVALID_LEN = ({"schema": "flywheel.evidence-transport-error/v1",
                 "error": {"code": "INVALID_LENGTH", "message": "request length is invalid"}}, 400)
_INVALID_OP = ({"schema": "flywheel.evidence-transport-error/v1",
                "error": {"code": "INVALID_REQUEST", "message": "gateway operation is invalid"}}, 422)


def post_session_tokens(h, p: str):
    length = h._content_length()
    if length is None:
        return h._json(*_INVALID_LEN)
    try:
        req = json.loads(h.rfile.read(length) or b"{}")
    except Exception:
        req = {}
    from harness.session_token_route import session_token_post
    return h._json(*session_token_post(p.rsplit("/", 1)[-1], req, owner_ref=h.owner_ref, token_store=h._session_tokens()))


def post_service_desk_review(h, p: str):
    length = h._content_length()
    if length is None:
        return h._json(*_INVALID_LEN)
    from harness.enterprise_envs.service_desk_review_route import service_desk_review_post
    return h._json(*service_desk_review_post(p, h.rfile.read(length), run_root=Path(h.run_root)))


def post_process_audit_review(h, p: str):
    from harness.incident_sim_process_audit_route import (
        MAX_PACKET_BYTES, is_json_content_type, payload_too_large_response,
        process_audit_review_post, unsupported_media_type_response,
    )
    length = h._content_length()
    if length is None:
        return h._json(*_INVALID_LEN)
    content_type = h.headers.get("Content-Type", "")
    if not is_json_content_type(content_type):
        return h._json(*unsupported_media_type_response())
    if length > MAX_PACKET_BYTES:
        return h._json(*payload_too_large_response())
    return h._json(*process_audit_review_post(p, h.rfile.read(length), content_type=content_type))


def _post_journey_extensions(h, p: str, raw: bytes):
    from harness.evidence_extension_contracts import capability_document as _empty_doc
    from harness.evidence_extension_route import (
        handle_capabilities, handle_domain_pack_project, handle_frontier_axis,
        handle_frontier_project, handle_incident_propose,
    )
    from harness.evidence_public import parse_json
    empty = _empty_doc(
        journey={"schema": "flywheel.evidence-journey-projection/v2", "event_head_sha256": "0" * 64},
        incident_contract=None, frontier_contract=None, pack_contracts=[], containment={"process": False})
    action = p.rsplit("/", 1)[-1]
    if action == "capabilities":
        return h._json(*handle_capabilities(empty))
    try:
        req = parse_json(raw)
    except Exception:
        req = {}
    dispatch = {
        "incident-propose": lambda: handle_incident_propose(req, empty),
        "frontier-project": lambda: handle_frontier_project(req, empty),
        "frontier-axis": lambda: handle_frontier_axis(req, empty, h.clock),
        "domain-pack-project": lambda: handle_domain_pack_project(req, empty),
    }
    if action in dispatch:
        return h._json(*dispatch[action]())
    return h._json({"schema": "flywheel.evidence-transport-error/v1",
                    "error": {"code": "NOT_FOUND", "message": "unknown extension"}}, 404)


def _post_continuation(h, p: str, raw: bytes, resolve_root_fn):
    from harness.continuation_route import handle_continuation_post
    resolved_root = None
    if p == "/api/continuation/preview":
        from harness.evidence_public import TransportError, error_response, parse_json
        try:
            req = parse_json(raw)
        except Exception:
            req = None
        if req is not None:
            resolved_root, err = resolve_root_fn(req.get("root"), h.root)
            if err:
                return h._json(*error_response(TransportError("ROOT_UNAVAILABLE", "workspace root is unavailable")))
    return h._json(*handle_continuation_post(
        p, raw, owner_ref=h.owner_ref, state_root=h.flywheel_home / "state", root=resolved_root, clock=h.clock))


def post_custody_route(h, p: str, resolve_root_fn):
    """Dispatch private-custody raw-body POST routes."""
    length = h._content_length()
    if length is None:
        return h._json(*_INVALID_LEN)
    raw = h.rfile.read(length)
    state_root = h.flywheel_home / "state"
    if p.startswith("/api/evidence/"):
        from harness.evidence_route import evidence_post
        return h._json(*evidence_post(p, raw, root=h.root))
    if p.startswith("/api/journeys/extensions/"):
        return _post_journey_extensions(h, p, raw)
    if p.startswith("/api/journeys/"):
        from harness.journey_route import journey_post
        return h._json(*journey_post(p, raw, owner_ref=h.owner_ref, state_root=state_root,
                                     evidence_root=state_root / "artifacts", clock=h.clock))
    if p.startswith("/api/source-context/"):
        from harness.source_context_route import source_context_post
        return h._json(*source_context_post(p, raw, owner_ref=h.owner_ref, state_root=state_root, clock=h.clock))
    if p.startswith("/api/context-memory/"):
        from harness.context_memory_route import context_memory_post
        return h._json(*context_memory_post(p, raw, owner_ref=h.owner_ref, state_root=state_root, clock=h.clock))
    if p.startswith("/api/agent/mcp/"):
        from harness.gateway_agent_mcp_route import agent_mcp_post
        return h._json(*agent_mcp_post(p, raw, owner_ref=h.owner_ref, state_root=state_root))
    if p.startswith("/api/continuation/"):
        return _post_continuation(h, p, raw, resolve_root_fn)
    if p.startswith("/api/grants/"):
        from harness.grant_route import grant_post
        return h._json(*grant_post(p, raw, owner_ref=h.owner_ref, state_root=state_root,
                                   evidence_root=state_root / "artifacts", clock=h.clock))
    if p.startswith("/api/writing/"):
        from harness.writing_route import writing_post
        return h._json(*writing_post(p, raw, owner_ref=h.owner_ref, state_root=state_root, clock=h.clock))
    if p.startswith("/api/gateway-grants/"):
        from harness.gateway_grant_route import gateway_grant_post
        reg = getattr(h._operation_components()[1], "provider_session_registry", None)
        return h._json(*gateway_grant_post(
            p, raw, owner_ref=h.owner_ref, run_root=Path(h.run_root), state_root=state_root,
            clock=h.clock, workspace_root=Path(h.root), provider_session_registry=reg))
    from harness.credential_handle_route import credential_handle_post
    return h._json(*credential_handle_post(p, raw, owner_ref=h.owner_ref, state_root=state_root))


def post_hooks(h, p: str):
    length = h._content_length()
    if length is None:
        return h._json(*_INVALID_OP)
    from harness.hooks_route import handle_hooks_post
    return h._json(*handle_hooks_post(
        p, h.rfile.read(length), run_root=h.run_root, owner_ref=h.owner_ref,
        state_root=h.flywheel_home / "state", clock=h.clock))


def post_subagents(h, p: str):
    req, fault = h._json_req()
    if fault:
        return h._json(*fault)
    from harness.subagents_route import handle_subagents_post
    service, factory = h._operation_components()
    return h._json(*handle_subagents_post(
        p, req, run_root=h.run_root, clock=h.clock, owner_ref=h.owner_ref,
        state_root=h.flywheel_home / "state", operation_service=service,
        process_factory=factory, workspace_root=Path(h.root)))


def post_json_surface(h, p: str):
    req, fault = h._json_req()
    if fault:
        return h._json(*fault)
    if p.startswith("/api/schedule/"):
        from harness.schedule_route import handle_schedule_post
        return h._json(*handle_schedule_post(p, req, run_root=h.run_root, clock=h.clock))
    if p == "/api/scan/vulnerabilities":
        from harness.scan_route import handle_scan_post
        return h._json(*handle_scan_post(p, req, root=h.root, run_root=h.run_root, clock=h.clock))
    if p.startswith("/api/runners/"):
        from harness.runner_route import handle_runners_post
        return h._json(*handle_runners_post(p, req, run_root=h.run_root, clock=h.clock))
    if p.startswith("/api/browser/"):
        from harness.browser_route import handle_browser_post
        return h._json(*handle_browser_post(p, req, run_root=h.run_root, clock=h.clock))
    from harness.skill_route import handle_skills_post
    return h._json(*handle_skills_post(p, req, run_root=h.run_root, clock=h.clock))


def authorize_post_action(h, p: str, auth_owner_fn) -> bool:
    """Authorize a granted gateway operation; returns True if the response was already sent."""
    from harness.gateway_operation import action_for_path, materialize_agent_attachment, thaw_operation
    action = action_for_path(p)
    if action is None:
        return False
    length = h._content_length()
    if length is None:
        h._json(*_INVALID_OP)
        return True
    from harness.gateway_grant_route import authorize_gateway_operation, gateway_error_response
    try:
        owner = h.owner_ref or (
            h.auth_token and auth_owner_fn(
                h.headers, "POST", h.auth_token, h.flywheel_home, allowed_hosts=h.allowed_hosts)[0]
        ) or None
        authorized = authorize_gateway_operation(
            action, h.rfile.read(length), owner_ref=owner,
            state_root=h.flywheel_home / "state", clock=h.clock)
        from harness.bulletin_access import authorized_bulletin_access_denial
        denied = authorized_bulletin_access_denial(authorized)
        if denied is not None:
            h._gateway_guarded = True
            h._json(denied, 403)
            return True
        from harness.gateway_provider_adapter import resolve_credentials
        authorized = resolve_credentials(authorized, h.flywheel_home / "state")
        h._gateway_guarded = True
    except Exception as exc:
        h._json(*gateway_error_response(exc))
        return True
    from harness.gateway_actions import dispatch_builtin
    try:
        dispatched = dispatch_builtin(authorized)
    except Exception as exc:
        h._json(*gateway_error_response(exc))
        return True
    if dispatched is not None:
        h._json(*dispatched)
        return True
    h._gateway_operation = materialize_agent_attachment(thaw_operation(authorized.operation))
    h._gateway_bindings = authorized.credential_bindings
    return False
