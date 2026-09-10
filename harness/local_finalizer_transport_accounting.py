"""Bind strict transport observations to a logical invocation, without inferring sends."""
from __future__ import annotations

import uuid

FIELDS = {"attempt_id", "phase", "method", "path", "connection_started",
          "request_send_started", "outcome", "code", "status"}
PREFLIGHT_CODES = {"route_not_allowed", "invalid_request_body", "request_too_large", "invalid_timeout"}


def validate_event(event):
    if not isinstance(event, dict) or set(event) != FIELDS:
        raise ValueError("invalid transport fields")
    if str(uuid.UUID(event["attempt_id"])) != event["attempt_id"]:
        raise ValueError("invalid transport identity")
    if (event["phase"] not in {"connection_attempt", "request_send_started", "terminal"}
            or event["method"] not in {"GET", "POST"}
            or event["path"] not in {"/api/chat", "/api/tags", "/generate", "/health"}
            or any(type(event[k]) is not bool for k in ("connection_started", "request_send_started"))):
        raise ValueError("invalid transport progression")
    if event["phase"] != "terminal":
        if any(event[k] is not None for k in ("outcome", "code", "status")):
            raise ValueError("invalid transport intent")
        flags = (event["connection_started"], event["request_send_started"])
        if flags != ((False, False) if event["phase"] == "connection_attempt" else (True, False)):
            raise ValueError("invalid pre-syscall progression")
    elif (event["outcome"] not in {"response", "error", "timeout"}
          or event["status"] is not None and (type(event["status"]) is not int or not 100 <= event["status"] <= 599)
          or event["code"] is not None and event["code"] not in {
              "response_received", "observer_failed", "deadline_exceeded", "timeout", "network_error",
              "response_too_large", "invalid_http_response", "invalid_json_response",
              "invalid_transport_limit", "redirect_not_allowed"}):
        raise ValueError("invalid transport terminal")
    if event["phase"] == "terminal":
        response = event["outcome"] == "response"
        if (event["request_send_started"] and not event["connection_started"]
                or response and (not event["request_send_started"] or event["status"] is None
                                 or event["code"] != "response_received")
                or not response and (event["status"] is not None or event["code"] in {None, "response_received"})):
            raise ValueError("terminal response contradicts local progression")


class TransportObservation:
    def __init__(self, stage, factory):
        self.stage, self.call_id = stage, None
        self.inner = factory(observer=self.event)

    def event(self, event):
        try:
            validate_event(event)
        except Exception:
            self.stage.context.fatal()
        if self.call_id is None:
            self.stage.context.fatal()
        self.stage.emit("transport", invocation_id=self.stage.current_invocation,
                        call_id=self.call_id, transport=dict(event))

    def __call__(self, method, url, body, timeout):
        if self.call_id is not None:
            raise ValueError("concurrent transport observation unsupported")
        self.call_id = str(uuid.uuid4())
        parent = self.stage.current_invocation
        self.stage.emit("transport_callable_started", call_id=self.call_id, invocation_id=parent)
        try:
            result = self.inner(method, url, body, timeout)
        except BaseException as exc:
            self.stage.check()
            no_io = (getattr(exc, "code", None) in PREFLIGHT_CODES
                     and hasattr(exc, "terminal_event") and exc.terminal_event is None)
            self.stage.emit("transport_callable_terminal", call_id=self.call_id,
                            invocation_id=parent, preflight_no_io=no_io)
            raise
        else:
            self.stage.check()
            self.stage.emit("transport_callable_terminal", call_id=self.call_id,
                            invocation_id=parent, preflight_no_io=False)
            return result
        finally:
            self.call_id = None


def transport_counts(events, starts):
    calls, attempts, seen_parents = {}, {}, set()
    observed = any(e["kind"] == "transport_observation_started" for e in events)
    for event in events:
        kind = event["kind"]
        if kind not in {"transport_callable_started", "transport_callable_terminal", "transport"}:
            continue
        parent, call_id = event["invocation_id"], event["call_id"]
        if kind == "transport_callable_started":
            if call_id in calls:
                raise ValueError("duplicate transport call")
            calls[call_id] = {"parent": parent, "terminal": None, "attempts": set()}
            if parent is not None:
                seen_parents.add(parent)
            continue
        if call_id not in calls or calls[call_id]["parent"] != parent or calls[call_id]["terminal"] is not None:
            raise ValueError("orphan transport observation")
        call = calls[call_id]
        if kind == "transport_callable_terminal":
            if type(event["preflight_no_io"]) is not bool:
                raise ValueError("invalid preflight disposition")
            call["terminal"] = event
            continue
        record = event["transport"]
        validate_event(record)
        identity = record["attempt_id"]
        if identity in attempts and attempts[identity]["call_id"] != call_id:
            raise ValueError("transport attempt parent collision")
        group = attempts.setdefault(identity, {"call_id": call_id, "records": []})
        group["records"].append(record)
        call["attempts"].add(identity)
    complete = observed and seen_parents == set(starts)
    sends = connections = responses = 0
    for call in calls.values():
        terminal = call["terminal"]
        if terminal is None:
            complete = False
        elif terminal["preflight_no_io"]:
            if call["attempts"]:
                raise ValueError("preflight disposition contradicts events")
        elif not call["attempts"]:
            complete = False
    for group in attempts.values():
        records = group["records"]
        phases = [e["phase"] for e in records]
        if phases not in (["terminal"], ["connection_attempt", "terminal"],
                          ["connection_attempt", "request_send_started", "terminal"]):
            if phases not in (["connection_attempt"], ["connection_attempt", "request_send_started"]):
                raise ValueError("transport progression order invalid")
            complete = False
            continue
        first, end = records[0], records[-1]
        if any((e["method"], e["path"]) != (first["method"], first["path"]) for e in records):
            raise ValueError("transport route changed")
        if (end["connection_started"] and "connection_attempt" not in phases
                or end["request_send_started"] and "request_send_started" not in phases
                or "request_send_started" in phases and not end["connection_started"]):
            raise ValueError("terminal contradicts observed intents")
        call = calls[group["call_id"]]
        if call["parent"] is not None and end["method"] == "POST":
            sends += end["request_send_started"]
            connections += end["connection_started"]
            responses += end["outcome"] == "response"
    return complete, sends, connections, responses, set(attempts)
