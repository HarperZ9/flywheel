"""browser_control.py -- driving a browser or a desktop, one admitted act at a time.

Each admitted driver call first reserves a budget slot on the durable action
chain. A correlated terminal records the driver's acknowledgement; absent or
uncertain delivery pauses actuation instead of inviting a retry. The policy
is fixed by the first record. With no driver bound the same grammar supports
explicit simulation, which does not establish a real browser origin.

What this is not: it is not a way past a control someone else put up. Typing
into a credential-shaped field is refused here whatever the policy says, a
non-http scheme never resolves, and there is no facility for solving a
challenge, rotating an address, or disguising what the client is.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

from .evidence_json import canonical_sha256
from . import browser_control_store as store
from .hash_chain import chain_intact as _chain_intact

EVENT_SCHEMA = "flywheel.browser-action/v1"
DIGEST_KEY = "action_sha256"

#: What an action may be. A grammar rather than free-form scripting, because
#: an admission rule can only be written against acts it can name.
KINDS = ("navigate", "read", "click", "type", "screenshot", "download")

#: The most acts one session may attempt. A cap turns a runaway loop into a
#: refusal with a reason instead of a bill and a browser history.
MAX_ACTIONS = 500

#: Field names that never receive typed text, whatever the policy allows.
#: The standing rule is that this system does not enter credentials; putting
#: it in the gate means a permissive policy cannot reach around it.
SECRET_FIELDS = ("password", "passwd", "pwd", "otp", "mfa", "2fa", "cvv",
                 "cvc", "card", "cardnumber", "ssn", "secret", "token",
                 "apikey", "api_key", "private_key", "seed_phrase")

_DRIVERS: dict = {}


class Refused(ValueError):
    """A malformed request, as opposed to an act the policy turned down."""


def _refuse(message: str) -> None:
    raise Refused(message)


def register_driver(name: str, run) -> None:
    """Bind something that can actually perform an admitted action.

    The seam exists so the gate can be tested, and shipped, without any
    actuation at all. A caller that binds nothing gets a session that decides
    and records; that is the default, and it is a supported way to run.
    """
    if not callable(run):
        _refuse("a driver must be callable")
    _DRIVERS[str(name)] = run


def clear_drivers() -> None:
    _DRIVERS.clear()


def bound_driver():
    """The single bound driver, or None. Two bound drivers is ambiguous."""
    if len(_DRIVERS) != 1:
        return None, None
    return next(iter(_DRIVERS.items()))


def chain_path(run_root, run_id: str) -> Path:
    """Where one session's chain lives. The name is checked, never repaired.

    Stripping the unwanted characters instead would map two different names
    onto one directory, so a caller asking for a session it named could be
    handed somebody else's history.
    """
    name = str(run_id or "")
    if not name or len(name) > 64:
        _refuse("run_id must be 1 to 64 characters")
    if not all(c.isalnum() or c in "_-." for c in name) or name.strip(".") == "":
        _refuse("run_id must hold letters, digits, dot, dash or underscore")
    return Path(run_root) / "browser" / name / "actions.json"


def chain_intact(records) -> bool:
    return _chain_intact(records, schema=EVENT_SCHEMA, digest_key=DIGEST_KEY)


def _origin(url: str) -> str:
    """The origin of an http(s) URL. Anything else has no origin here.

    file:// and data: are refused rather than normalised. A browser seam that
    resolves them is a local-disk read primitive wearing a browser's name.
    """
    parts = urlsplit(str(url or ""))
    if parts.scheme not in ("http", "https") or not parts.netloc:
        _refuse(f"not an http or https URL: {url!r}")
    return f"{parts.scheme}://{parts.netloc}".lower()


def _policy(raw: dict) -> dict:
    if not isinstance(raw, dict):
        _refuse("policy must be an object")
    origins = raw.get("origins")
    if not isinstance(origins, list) or not origins:
        _refuse("policy.origins must name at least one origin")
    allowed = sorted({_origin(o) for o in origins})
    refused = sorted({str(k) for k in raw.get("refuse_kinds", [])})
    unknown = [k for k in refused if k not in KINDS]
    if unknown:
        _refuse(f"policy.refuse_kinds names no such action: {unknown[0]}")
    try:
        cap = int(raw.get("max_actions", MAX_ACTIONS))
    except (TypeError, ValueError):
        _refuse("policy.max_actions must be a whole number")
    if not 1 <= cap <= MAX_ACTIONS:
        _refuse(f"policy.max_actions must be 1 to {MAX_ACTIONS}")
    return {"origins": allowed, "refuse_kinds": refused, "max_actions": cap}


def _action(raw: dict) -> dict:
    if not isinstance(raw, dict):
        _refuse("action must be an object")
    kind = str(raw.get("kind", ""))
    if kind not in KINDS:
        _refuse(f"unknown action kind: {kind!r}")
    action = {"kind": kind, "field": str(raw.get("field", "")),
              "selector": str(raw.get("selector", ""))[:200], "url": ""}
    if kind in ("navigate", "download"):
        action["url"] = str(raw.get("url", ""))
        _origin(action["url"])
    return action


_state = store.fold


def _verdict(action: dict, state: dict) -> tuple:
    """Admit or refuse one action. Returns (admitted, reason, origin).

    Order matters. The credential rule is checked before the policy so that
    no policy can be written that permits it.
    """
    policy = state["policy"]
    if action["kind"] == "type":
        field = action["field"].lower().replace("-", "").replace(" ", "")
        if any(mark in field for mark in SECRET_FIELDS):
            return False, f"typing into a credential field ({action['field']})", None
    if state["attempted"] >= policy["max_actions"]:
        return False, f"the session cap of {policy['max_actions']} is spent", None
    if action["kind"] in policy["refuse_kinds"]:
        return False, f"the policy refuses {action['kind']}", None
    if action["kind"] in ("navigate", "download"):
        origin = _origin(action["url"])
        if origin not in policy["origins"]:
            return False, f"{origin} is not an allowed origin", None
        return True, "", origin
    if state["origin"] is None:
        return False, "no page is open, so there is nothing to act on", None
    return True, "", state["origin"]


def _open(run_root, run_id: str):
    path = chain_path(run_root, run_id)
    try:
        return path, store.load(path)
    except store.BrowserStoreError as exc:
        if str(exc) == "BROWSER_HISTORY_INVALID":
            _refuse("the action chain for this session is broken")
        raise


def _write(path, records, record: dict) -> dict:
    return store.append(path, records, record)


def open_session(run_root, *, run_id: str, policy: dict, at: str) -> dict:
    """Fix the policy durably before any admission."""
    settled = _policy(policy)
    with store.guard(chain_path(run_root, run_id)):
        path, records = _open(run_root, run_id)
        if _state(records)["policy"] is not None:
            _refuse(f"session {run_id} already has a policy")
        return _write(path, records, {"kind": "policy", "at": at,
                                      "run_id": str(run_id), "policy": settled})


def _request_id(value, driver) -> str:
    if value is None and driver is None:
        return uuid4().hex
    if (not isinstance(value, str) or not 1 <= len(value) <= 128
            or not value.isascii() or any(not (c.isalnum() or c in "_.:-") for c in value)):
        _refuse("request_id must identify each driver-bound request (1 to 128 characters)")
    return value


def _complete(driver, wanted, admission):
    """A driver acknowledgement is a report, not independent semantic truth."""
    terminal = dict(admission, kind="completion", phase="completed",
                    admission_sha256=admission[DIGEST_KEY],
                    performed=None, delivery_status="unknown", error_code="")
    terminal.pop(DIGEST_KEY)
    interrupted = None
    try:
        outcome = driver(dict(wanted, origin=admission["origin"],
                              run_id=admission["run_id"], request_id=admission["request_id"]))
        terminal["result_sha256"] = canonical_sha256(outcome)
        if isinstance(outcome, dict) and outcome.get("performed") is False:
            terminal.update(performed=False, delivery_status="driver_reported_not_performed")
        elif (isinstance(outcome, dict) and outcome.get("performed") is True
              and outcome.get("ok") is True):
            terminal.update(performed=True, delivery_status="driver_reported_performed")
        else:
            terminal["error_code"] = "DRIVER_ACKNOWLEDGEMENT_UNKNOWN"
    except BaseException as exc:
        terminal["error_code"] = "DRIVER_EXCEPTION"
        if not isinstance(exc, Exception):
            interrupted = exc
    return terminal, interrupted


def attempt(run_root, *, run_id: str, action: dict, at: str, request_id=None) -> dict:
    """Reserve one attempt before dispatch; uncertain delivery never retries."""
    wanted = _action(action)
    name, driver = bound_driver()
    identity = _request_id(request_id, driver)
    with store.guard(chain_path(run_root, run_id)):
        path, records = _open(run_root, run_id)
        state = _state(records)
        if state["policy"] is None:
            _refuse(f"session {run_id} has no policy yet")
        previous = state["requests"].get(identity)
        if previous is not None:
            result = state["actions"][previous]
            if result["action"] != wanted:
                _refuse("request_id already binds a different action")
            return result
        if driver is not None:
            state["origin"] = state["live_origin"]
        admitted, reason, origin = _verdict(wanted, state)
        if driver is not None and state["delivery_unknown"]:
            admitted, reason, origin = False, "previous delivery is unknown; reconcile before further actuation", None
        dispatch = admitted and driver is not None
        admission = _write(path, records, {
            "kind": "action", "at": at, "run_id": str(run_id), "request_id": identity,
            "seq": state["attempted"] + 1, "action": wanted,
            "admitted": admitted, "reason": reason, "origin": origin,
            "driver": name if dispatch else None, "simulated": driver is None,
            "phase": "admitted" if dispatch else "settled",
            "performed": None if dispatch else False, "result_sha256": "",
            "delivery_status": "unknown" if dispatch else "not_dispatched"})
        if not dispatch:
            return admission
        terminal, interrupted = _complete(driver, wanted, admission)
        completed = _write(path, records, terminal)
        if interrupted is not None:
            raise interrupted
        return completed


def session(run_root, *, run_id: str) -> dict:
    """Return one action per reservation, correlated with its terminal record."""
    intact = True
    try:
        records = store.load(chain_path(run_root, run_id))
    except store.BrowserStoreError as exc:
        if str(exc) != "BROWSER_HISTORY_INVALID":
            raise
        intact, records = False, []
    state = _state(records)
    acts = state["actions"]
    name, _ = bound_driver()
    return {"chain_intact": intact, "run_id": str(run_id),
            "policy": state["policy"], "open_origin": state["origin"],
            "driver_open_origin": state["live_origin"],
            "delivery_unknown": state["delivery_unknown"], "driver": name,
            "actions": acts, "attempted": len(acts),
            "admitted": sum(1 for a in acts if a["admitted"]),
            "refused": sum(1 for a in acts if not a["admitted"]),
            "performed": sum(1 for a in acts if a["performed"] is True)}


def sessions(run_root) -> list:
    """Every session under this run root, newest name last."""
    home = Path(run_root) / "browser"
    if not home.is_dir():
        return []
    return sorted(d.name for d in home.iterdir()
                  if (d / "actions.json").is_file())
