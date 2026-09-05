"""workstream_instrument.py -- an instrument record against its driver reference.

An `instrument` obligation used to be carried. The example said as much in
words: the driver caps dispense flow at 200 uL/s, the run asked for 140, the cap
is enforced at the device, and nothing here re-checks it. That sentence is honest
and it is also the whole problem, because a stack whose device claims are all
assumptions is a stack where the interesting failures are invisible.

This repository does not talk to instruments and should not pretend to. What it
can do is check a record against the reference file the driver ships, which is
where a real high-throughput screening pipeline finds most of its bad runs
anyway. Five refutations are available without touching hardware:

  a command the driver does not have
  a parameter the reference does not list for that command
  a parameter outside the limit the driver enforces
  a reading outside the range the device can produce
  a run dated before its own calibration, or after that calibration expired

What passes is narrower than it sounds, and the caveat says so: a passing record
is internally consistent with the driver's own reference file. It is not evidence
that the device did this, that the sample was the right one, or that the reading
is accurate. Those need the device, and the device is not here.

The environment pins the device and driver as `mhs:<device>/driver-<version>`,
and it binds the same way a Lean version does. A reference for a different driver
settles unverifiable rather than passing, because a limit table from another
release is not the one the run was subject to.

The reference path comes from the caller, never from the declaration. A
declaration is data a stranger writes, and a file path read out of one is a
file-read surface with a schema on top.

    {"schema": "flywheel.mhs.reference/v1", "device": "liquid-handler-2",
     "driver": "1.4.0", "calibration_valid_days": 30,
     "commands": {"dispense": {
        "parameters": {"flow_rate_ul_s": {"min": 1, "max": 200}},
        "readings": {"volume_ul": {"min": 0, "max": 1000}}}}}
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from harness.evidence_json import strict_load_json
from harness.workstream import Obligation, WorkstreamError

REFERENCE_SCHEMA = "flywheel.mhs.reference/v1"

_ENVIRONMENT = re.compile(r"mhs:([^/\s]+)/driver-(\S+)")
_MAX_REFERENCE = 4_000_000
_MAX_RECORD = 20_000
_DAY_SECONDS = 86_400


def load_reference(path: str | Path) -> dict:
    """Read one driver reference file, and insist on its shape before use."""
    source = Path(path)
    if not source.is_file():
        raise WorkstreamError(f"no driver reference at {path}")
    body = strict_load_json(source.read_text(encoding="utf-8"), max_bytes=_MAX_REFERENCE)
    if body.get("schema") != REFERENCE_SCHEMA:
        raise WorkstreamError(f"{path} is not a {REFERENCE_SCHEMA} document")
    for field in ("device", "driver"):
        if not isinstance(body.get(field), str) or not body[field].strip():
            raise WorkstreamError(f"a driver reference names its {field}")
    if not isinstance(body.get("commands"), dict) or not body["commands"]:
        raise WorkstreamError("a driver reference lists at least one command")
    return body


def load_references(paths) -> dict[str, dict]:
    """Several reference files, keyed by the device each one describes."""
    found: dict[str, dict] = {}
    for path in paths or ():
        reference = load_reference(path)
        key = reference["device"].lower()
        if key in found:
            raise WorkstreamError(f"two references describe {reference['device']}")
        found[key] = reference
    return found


def _when(value: object, field: str) -> datetime:
    """An ISO-8601 stamp. A naive one is read as UTC, and that is a choice."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        # Named, because a record carries two timestamps and "invalid isoformat"
        # on its own does not say which one a reader has to go fix.
        raise ValueError(f"{field} must be an ISO-8601 timestamp: {exc}") from exc
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _record(obligation: Obligation) -> dict:
    """The run record, with the fields every instrument record must carry."""
    body = strict_load_json(obligation.statement, max_bytes=_MAX_RECORD)
    for field in ("device", "command"):
        if not isinstance(body.get(field), str) or not body[field].strip():
            raise ValueError(f"an instrument record names its {field}")
    for field in ("parameters", "readings"):
        if field in body and not isinstance(body[field], dict):
            raise ValueError(f"{field} is an object of name to number")
    return body


def _numbers(block: object, field: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for name, value in (block or {}).items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{field}.{name} must be a number")
        values[name] = float(value)
    return values


def _within(values: dict[str, float], limits: object, field: str) -> str | None:
    """The first value the reference refuses, or None if it refuses none."""
    table = limits if isinstance(limits, dict) else {}
    for name in sorted(values):
        bound = table.get(name)
        if not isinstance(bound, dict):
            return f"the reference lists no {field} named {name} for this command"
        value = values[name]
        low, high = bound.get("min"), bound.get("max")
        if isinstance(low, (int, float)) and value < low:
            return f"{field} {name} is {value} and the reference floor is {low}"
        if isinstance(high, (int, float)) and value > high:
            return f"{field} {name} is {value} and the reference limit is {high}"
    return None


def _calibration(body: dict, reference: dict) -> str | None:
    """Whether the run sits inside a calibration that governs it."""
    window = reference.get("calibration_valid_days")
    if not isinstance(window, (int, float)) or isinstance(window, bool):
        return None
    observed = _when(body.get("observed_at"), "observed_at")
    calibrated = _when(body.get("calibrated_at"), "calibrated_at")
    age = (observed - calibrated).total_seconds()
    if age < 0:
        return "the run is dated before the calibration it claims to run under"
    if age > window * _DAY_SECONDS:
        return (f"the calibration is {age / _DAY_SECONDS:.1f} days before the run "
                f"and the reference allows {window}")
    return None


def _binds(obligation: Obligation,
           references: dict[str, dict]) -> tuple[dict | None, str, str]:
    """The reference and device this obligation is subject to, or why none is."""
    pin = _ENVIRONMENT.search(obligation.environment or "")
    if pin is None:
        return None, "", ("the environment does not name a device and driver as "
                          "mhs:<device>/driver-<version>, so no reference binds it")
    device, driver = pin.group(1), pin.group(2)
    reference = references.get(device.lower())
    if reference is None:
        return None, device, f"no driver reference for {device} was supplied"
    if reference["driver"] != driver:
        return None, device, (f"the environment pins {device} driver {driver} and the "
                              f"reference describes {reference['driver']}")
    return reference, device, ""


def instrument_checker(references: dict[str, dict] | None = None):
    """A checker over driver reference files, keyed by device.

    With no reference for a device the obligation settles unverifiable, never
    passing: an unchecked device claim reported as verified is the failure this
    kind exists to prevent.
    """
    known = dict(references or {})

    def check(obligation: Obligation) -> tuple[str, str]:
        reference, device, refusal = _binds(obligation, known)
        if reference is None:
            return "UNVERIFIABLE", refusal
        try:
            body = _record(obligation)
            if body["device"].lower() != device.lower():
                return "UNVERIFIABLE", (f"the record names {body['device']} and the "
                                        f"environment pins {device}")
            command = reference["commands"].get(body["command"])
            if not isinstance(command, dict):
                return "FAIL", f"the reference lists no command named {body['command']}"
            parameters = _numbers(body.get("parameters"), "parameters")
            readings = _numbers(body.get("readings"), "readings")
            refused = (_within(parameters, command.get("parameters"), "parameter")
                       or _within(readings, command.get("readings"), "reading")
                       or _calibration(body, reference))
        except (TypeError, ValueError) as exc:
            return "FAIL", f"the statement is not a readable instrument record: {exc}"
        if refused:
            return "FAIL", refused
        return "PASS", (f"{body['command']} on {reference['device']} driver "
                        f"{reference['driver']}: {len(parameters)} parameter(s) and "
                        f"{len(readings)} reading(s) inside the reference")

    return check
