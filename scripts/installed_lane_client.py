"""The engine routes the desktop app calls, driven over HTTP.

Every lane call, tool listing and setting the app makes is a granted
operation bound to a Journey. The app shows the approval sheet and the person
approves once; here the harness approves the exact proposal it prepared. The
Journey is created through the same routes (``/api/grants/prepare/create``,
``approve-once``, ``/api/journeys/create``) from an intake file the harness
places in the home's artifact folder, as a person's import would.

A refusal at any stage comes back as ``(status, body)`` with ``stage`` added,
so a check can read the code whether the engine refused at prepare or at the
call. Nothing here writes the token anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path
import urllib.error
import urllib.request

OPERATION_SCHEMA = "flywheel.gateway-operation/v1"
# Loopback only: never route the engine calls through a proxy the host sets.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Gateway:
    def __init__(self, base: str, token: str) -> None:
        self.base, self._token = base, token

    def request(self, method: str, path: str, body: object = None,
                timeout: float = 90.0) -> tuple[int, object]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self._token}", "Content-Type": "application/json"})
        try:
            with _OPENER.open(req, timeout=timeout) as resp:
                return resp.status, _decode(resp.read())
        except urllib.error.HTTPError as err:
            return err.code, _decode(err.read())
        except (OSError, TimeoutError) as err:
            return 0, {"code": "TRANSPORT_ERROR", "error": type(err).__name__}

    def roster(self) -> dict:
        status, body = self.request("GET", "/api/lanes", timeout=30)
        return body if status == 200 and isinstance(body, dict) else {}


def _decode(raw: bytes) -> object:
    try:
        return json.loads(raw or b"{}")
    except ValueError:
        return {"non_json_bytes": len(raw)}


def _stage(status: int, body: object, stage: str) -> tuple[int, object]:
    if isinstance(body, dict):
        return status, {**body, "stage": stage}
    return status, {"stage": stage, "body": body}


class GrantedCalls:
    """One Journey and the granted operations made under it."""

    def __init__(self, gateway: Gateway, home: Path, tag: str) -> None:
        self.gw, self.home, self.tag = gateway, home, tag
        self.journey_ref = self.head = None
        self._n = 0

    def _rid(self, label: str) -> str:
        self._n += 1
        return f"wp11-{self.tag}-{self._n:03d}-{label}"[:120]

    def open_journey(self) -> tuple[int, object]:
        intake_ref = f"wp11/intake-{self.tag}.json"
        path = self.home / "state" / "artifacts" / intake_ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema": "flywheel.wp11-intake/v1",
                                    "purpose": "installed-app lane acceptance"}),
                        encoding="utf-8")
        req = {"goal": "installed-app lane acceptance", "intake_ref": intake_ref,
               "client_request_id": self._rid("journey")}
        status, prop = self.gw.request("POST", "/api/grants/prepare/create", req)
        if status != 200:
            return _stage(status, prop, "journey_prepare")
        status, grant = self.gw.request("POST", "/api/grants/approve-once",
                                        {"proposal_ref": prop.get("proposal_ref")})
        if status != 200:
            return _stage(status, grant, "journey_approve")
        status, ack = self.gw.request("POST", "/api/journeys/create",
                                      {**req, "grant_ref": grant.get("grant_ref")})
        if status == 200 and isinstance(ack, dict):
            self.journey_ref, self.head = ack.get("journey_ref"), ack.get("event_head_sha256")
        return status, ack

    def granted(self, action: str, operation: dict, route: str, *,
                timeout: float = 90.0) -> tuple[int, object]:
        """Prepare, approve once, then send the operation to its route."""
        env = {"schema": OPERATION_SCHEMA, "journey_ref": self.journey_ref,
               "expected_event_head": self.head, "client_request_id": self._rid(action)}
        status, prop = self.gw.request("POST", f"/api/gateway-grants/prepare/{action}",
                                       {**env, "operation": operation})
        if status != 200:
            return _stage(status, prop, "prepare")
        status, grant = self.gw.request("POST", "/api/gateway-grants/approve-once",
                                        {"proposal_ref": prop.get("proposal_ref")})
        if status != 200:
            return _stage(status, grant, "approve")
        return self.gw.request("POST", route, {**env, "grant_ref": grant.get("grant_ref"),
                                               **operation}, timeout=timeout)

    def lane_call(self, lane: str, tool: str, args: dict, *, tier: str = "T1",
                  timeout_s: int = 300) -> tuple[int, object]:
        op = {"name": lane, "tool": tool, "args": args, "governance_tier": tier,
              "timeout": timeout_s, "data_refs": [], "credential_refs": []}
        return self.granted("lane.call", op, f"/api/lane/{lane}/{tool}",
                            timeout=timeout_s + 60)

    def list_tools(self, lane: str) -> tuple[int, object]:
        op = {"name": lane, "data_refs": [], "credential_refs": []}
        return self.granted("plugin.probe", op, f"/api/lanes/{lane}/tools", timeout=180)

    def set_local_model_root(self, folder: Path) -> tuple[int, object]:
        op = {"path": str(folder), "data_refs": [], "credential_refs": []}
        return self.granted("lane.root", op, "/api/lanes/local-model/root")

    def check_lane(self, lane: str) -> tuple[int, object]:
        return self.gw.request("POST", f"/api/lanes/{lane}/check", {}, timeout=120)
