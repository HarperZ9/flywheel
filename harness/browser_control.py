"""browser_control.py -- driving a browser or a desktop, one admitted act at a time.

Agents that operate a screen are usually shipped as a capability with a log
bolted beside it. The log records what the tool did, which is the wrong half:
by the time a line appears, the click has happened. Nothing in it can say why
the click was allowed, and a refusal leaves no trace at all, so the quietest
run and the most constrained run look identical afterwards.

Here the gate and the record are the same write. Every attempt lands on an
append-only chain carrying the verdict, admitted or refused, before anything
touches a screen. The policy that decided it is the chain's first record, so
loosening the rules to explain a bad afternoon breaks the citation on every
action that followed.

Actuation sits behind a driver seam. With no driver bound the session admits,
records, and reports `performed: false`, which is an honest null rather than a
pretend success. The driver shipped with the tests records what it was asked
to do and touches nothing.

What this is not: it is not a way past a control someone else put up. Typing
into a credential-shaped field is refused here whatever the policy says, a
non-http scheme never resolves, and there is no facility for solving a
challenge, rotating an address, or disguising what the client is.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from .evidence_json import canonical_sha256
from .hash_chain import append_sealed, head_digest, load_chain, seal
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


def _state(records) -> dict:
    """Fold the chain into the policy, the open origin, and the count."""
    policy, origin, attempted = None, None, 0
    for record in records:
        if record.get("kind") == "policy":
            policy = record["policy"]
        else:
            attempted += 1
            if record["admitted"] and record["action"]["kind"] == "navigate":
                origin = record["origin"]
    return {"policy": policy, "origin": origin, "attempted": attempted}


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
    records = load_chain(path)
    if records and not chain_intact(records):
        _refuse("the action chain for this session is broken")
    return path, records


def _write(path, records, record: dict) -> dict:
    sealed = seal(dict(record, schema=EVENT_SCHEMA,
                       prev_sha256=head_digest(records, digest_key=DIGEST_KEY)),
                  digest_key=DIGEST_KEY)
    append_sealed(sealed, path=path, schema=EVENT_SCHEMA, digest_key=DIGEST_KEY)
    return sealed


def open_session(run_root, *, run_id: str, policy: dict, at: str) -> dict:
    """Start a session by writing the policy that will judge every act."""
    settled = _policy(policy)
    path, records = _open(run_root, run_id)
    if _state(records)["policy"] is not None:
        _refuse(f"session {run_id} already has a policy")
    return _write(path, records, {"kind": "policy", "at": at,
                                  "run_id": str(run_id), "policy": settled})


def attempt(run_root, *, run_id: str, action: dict, at: str) -> dict:
    """Judge one action, record the verdict, and perform it if admitted.

    A refusal is written too. A gate that records only what it allowed cannot
    be audited for what it turned down, and the turned-down half is the half
    somebody will argue about later.
    """
    wanted = _action(action)
    path, records = _open(run_root, run_id)
    state = _state(records)
    if state["policy"] is None:
        _refuse(f"session {run_id} has no policy yet")
    admitted, reason, origin = _verdict(wanted, state)
    name, driver = bound_driver()
    performed, result = False, ""
    if admitted and driver is not None:
        outcome = driver(dict(wanted, origin=origin, run_id=str(run_id)))
        performed, result = True, canonical_sha256(
            outcome if isinstance(outcome, dict) else {"value": str(outcome)})
    return _write(path, records, {
        "kind": "action", "at": at, "run_id": str(run_id),
        "seq": state["attempted"] + 1, "action": wanted,
        "admitted": admitted, "reason": reason, "origin": origin,
        "driver": name if admitted else None,
        "performed": performed, "result_sha256": result})


def session(run_root, *, run_id: str) -> dict:
    """One session's policy, verdicts and counts, chain verdict at the top."""
    records = load_chain(chain_path(run_root, run_id))
    intact = chain_intact(records) if records else True
    state = _state(records) if intact else {"policy": None, "origin": None,
                                            "attempted": 0}
    acts = [r for r in records if r.get("kind") == "action"] if intact else []
    name, _ = bound_driver()
    return {"chain_intact": intact,
            "run_id": str(run_id),
            "policy": state["policy"],
            "open_origin": state["origin"],
            "driver": name,
            "actions": acts,
            "attempted": len(acts),
            "admitted": sum(1 for a in acts if a["admitted"]),
            "refused": sum(1 for a in acts if not a["admitted"]),
            "performed": sum(1 for a in acts if a["performed"])}


def sessions(run_root) -> list:
    """Every session under this run root, newest name last."""
    home = Path(run_root) / "browser"
    if not home.is_dir():
        return []
    return sorted(d.name for d in home.iterdir()
                  if (d / "actions.json").is_file())
