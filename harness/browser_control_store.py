"""Durable browser admissions using the shared chain and file-lock primitives."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from .evidence_json import canonical_bytes, strict_load_json
from .hash_chain import chain_intact, head_digest, seal
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy, fsync_directory

SCHEMA = "flywheel.browser-action/v1"
DIGEST = "action_sha256"
MAX_BYTES = 8 * 1024 * 1024


class BrowserStoreError(RuntimeError):
    """Fixed public error; filesystem paths and driver payloads stay private."""


def guard(path: Path):
    return ExclusiveJourneyLock.acquire(path.with_name("actions.lock"))


def load(path: Path) -> list:
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise BrowserStoreError("BROWSER_STORE_UNAVAILABLE") from exc
    try:
        if len(data) > MAX_BYTES:
            raise ValueError("history exceeds byte limit")
        # Keep the existing on-disk list while using the shared strict loader,
        # whose public format requires an object. Extra envelope keys refuse.
        envelope = strict_load_json(b'{"records":' + data + b'}',
                                    max_bytes=MAX_BYTES + 12, max_depth=33)
        if set(envelope) != {"records"}:
            raise ValueError("invalid history envelope")
        rows = envelope["records"]
        if not isinstance(rows, list) or not chain_intact(rows, schema=SCHEMA,
                                                        digest_key=DIGEST):
            raise ValueError("invalid history")
        fold(rows)
        return rows
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise BrowserStoreError("BROWSER_HISTORY_INVALID") from exc


def append(path: Path, records: list, record: dict) -> dict:
    """Caller holds guard through admission and terminal persistence."""
    sealed = seal(dict(record, schema=SCHEMA,
                       prev_sha256=head_digest(records, digest_key=DIGEST)),
                  digest_key=DIGEST)
    updated = [*records, sealed]
    fold(updated)
    data = canonical_bytes(updated)
    if len(data) > MAX_BYTES:
        raise BrowserStoreError("BROWSER_HISTORY_FULL")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        with path.open("r+b") as stream:
            os.fsync(stream.fileno())
        # The guard creates session parents; flush their directory entries too.
        for directory in (path.parent, path.parent.parent,
                          path.parent.parent.parent, path.parent.parent.parent.parent):
            fsync_directory(directory)
    except OSError as exc:
        raise BrowserStoreError("BROWSER_STORE_UNAVAILABLE") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    records.append(sealed)
    return sealed


def fold(records: list) -> dict:
    """One budget slot per admission, with correlated terminal evidence."""
    policy, planned, live = None, None, None
    actions, by_digest, requests = [], {}, {}
    for record in records:
        kind = record.get("kind")
        if kind == "policy":
            if policy is not None or actions:
                raise ValueError("policy must be first and unique")
            policy = record["policy"]
        elif kind == "action":
            _delivery(record)
            if policy is None or record["seq"] != len(actions) + 1:
                raise ValueError("invalid admission sequence")
            actions.append(record)
            by_digest[record[DIGEST]] = len(actions) - 1
            request_id = record.get("request_id")
            if request_id:
                if request_id in requests:
                    raise ValueError("duplicate request identifier")
                requests[request_id] = len(actions) - 1
        elif kind == "completion":
            _delivery(record)
            index = by_digest[record["admission_sha256"]]
            admission = actions[index]
            if admission["kind"] != "action" or admission.get("phase") != "admitted":
                raise ValueError("completion needs an unsettled admission")
            for key in ("seq", "run_id", "request_id", "action", "origin", "driver",
                        "admitted", "simulated", "reason"):
                if record[key] != admission[key]:
                    raise ValueError("completion binding differs")
            actions[index] = record
        else:
            raise ValueError("unknown browser event")
    paused = False
    for index, action in enumerate(actions):
        if "phase" not in action:
            # Preserve raw history, but legacy driver returns did not carry
            # explicit acknowledgement and cannot authorize live navigation.
            action = dict(action, performed=None if action.get("driver") else False,
                          delivery_status="unknown" if action.get("driver") else "not_dispatched")
            actions[index] = action
        delivery = action.get("delivery_status")
        if action.get("driver") and delivery not in (
                "driver_reported_performed", "driver_reported_not_performed"):
            paused = True
        if action["admitted"] and action["action"]["kind"] == "navigate":
            if delivery == "driver_reported_performed":
                live = planned = action["origin"]
            elif not action.get("driver"):
                planned = action["origin"]
    return {"policy": policy, "origin": planned, "live_origin": live,
            "attempted": len(actions), "actions": actions,
            "requests": requests, "delivery_unknown": paused}


def _delivery(record: dict) -> None:
    """A valid digest cannot bless an impossible delivery-state combination."""
    phase, performed = record.get("phase"), record.get("performed")
    if "phase" not in record and record["kind"] == "action":
        if any(key in record for key in ("delivery_status", "request_id", "simulated",
                                         "admission_sha256", "error_code")):
            raise ValueError("mixed legacy and admission delivery fields")
        return  # Genuine legacy history is projected as non-authoritative.
    if type(record.get("admitted")) is not bool or type(record.get("simulated")) is not bool:
        raise ValueError("invalid action flags")
    if performed is not None and type(performed) is not bool:
        raise ValueError("invalid performed value")
    status = record.get("delivery_status")
    if record["kind"] == "action" and phase == "settled":
        valid = performed is False and status == "not_dispatched" and record.get("driver") is None
    elif (record["admitted"] is True and record["simulated"] is False
          and isinstance(record.get("driver"), str) and record["driver"]):
        if record["kind"] == "action" and phase == "admitted":
            valid = performed is None and status == "unknown" and record.get("result_sha256") == ""
        elif record["kind"] == "completion" and phase == "completed":
            expected = ("unknown" if performed is None else "driver_reported_performed"
                        if performed else "driver_reported_not_performed")
            digest = record.get("result_sha256", "")
            valid = status == expected and (performed is None or (
                isinstance(digest, str) and len(digest) == 64
                and all(c in "0123456789abcdef" for c in digest)))
        else:
            valid = False
    else:
        valid = False
    if not valid:
        raise ValueError("invalid delivery state")
