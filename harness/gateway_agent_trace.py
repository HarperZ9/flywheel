"""Immutable owner-bound private agent records, with verified bounded reads."""
from __future__ import annotations

from dataclasses import asdict
import logging
from pathlib import Path
import os
import re

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .gateway_agent_projection import projection
from .gateway_operation_validation import OPERATION_REF_PATTERN, validate_operation_value
from .gateway_secret_validation import validate_no_raw_secrets
from .journey_types import JOURNEY_REF_PATTERN
from .local_session import SessionLedger
from .operation_grants import OWNER_REF_PATTERN, _secure_owner_only
from .private_artifact_fs import (ArtifactIdentity, PrivateArtifactError,
                                  open_artifact_root, root_identity)

SCHEMA = "flywheel.gateway-agent-record/v1"
MAX_RECORD_BYTES = 8 * 1024 * 1024
MAX_TRACE_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 2048
# One record and 64 KiB stay reserved for the fixed failure record (EN-C3).
REGULAR_RECORDS = MAX_RECORDS - 1
REGULAR_BYTES = MAX_TRACE_BYTES - 64 * 1024
MAX_FAILURE_BYTES = 1024
GENESIS = "0" * 64
KINDS = {"request", "ledger", "progress", "result", "failure"}
FAILURE_SCHEMA = "flywheel.gateway-agent-failure/v1"
FAILURE_CLASSES = ("credential_refused", "size_bound", "custody_error", "schema_error")
_RULE = re.compile(r"[A-Za-z0-9_]{1,64}\Z")
_log = logging.getLogger(__name__)


class TraceError(ValueError):
    """The public code stays PRIVATE_TRACE_UNAVAILABLE; the class and the
    catalog rule are private and reach only the reserved failure record."""

    def __init__(self, failure_class: str = "custody_error", rule: str | None = None):
        super().__init__("PRIVATE_TRACE_UNAVAILABLE")
        self.failure_class, self.rule = failure_class, rule


def _private_value(value, secrets, *, result=False):
    """Only the router's exact runtime block has a private typed exception.

    The gateway secret grammar remains unchanged for public data. Long text is
    scanned in overlapping windows; exact approved values are checked whole.
    """
    validate_operation_value(value, secrets)
    def check_keys(item):
        if type(item) is dict:
            validate_operation_value(list(item), secrets)
            for child in item.values(): check_keys(child)
        elif type(item) is list:
            for child in item: check_keys(child)
    check_keys(value)
    if result and type(value) is dict and "environment" in value:
        env = value["environment"]
        if (type(env) is not dict or set(env) != {"python", "platform", "machine"}
                or any(type(v) is not str or len(v) > 512 for v in env.values())):
            raise TraceError()
        validate_no_raw_secrets(env)
        value = {k: v for k, v in value.items() if k != "environment"}
    def bounded(item):
        if type(item) is str and len(item) > 60_000:
            # Check all windows; preserve original bytes in the stored record.
            for offset in range(0, len(item), 30_000):
                validate_no_raw_secrets(item[offset:offset + 60_000])
            return "[validated long private text]"
        if type(item) is dict:
            return {k: bounded(v) for k, v in item.items()}
        if type(item) is list:
            return [bounded(v) for v in item]
        return item
    validate_no_raw_secrets(bounded(value))


def validate_private_trace_value(value, secrets=(), *, result=False):
    _private_value(value, tuple(secrets), result=result)


class AgentTrace:
    def __init__(self, state_root: Path, owner_ref: str, journey_ref: str,
                 operation_ref: str, *, secrets=(), expected_identity=None):
        try:
            for value, pattern in ((owner_ref, OWNER_REF_PATTERN),
                    (journey_ref, JOURNEY_REF_PATTERN), (operation_ref, OPERATION_REF_PATTERN)):
                if type(value) is not str or pattern.fullmatch(value) is None:
                    raise TraceError()
            self.root = Path(state_root)
            self.identity = (ArtifactIdentity.from_json_dict(expected_identity)
                if expected_identity is not None else root_identity(self.root))
            self.binding = {"owner_ref": owner_ref, "journey_ref": journey_ref,
                            "operation_ref": operation_ref}
            self.ref = "agt_" + canonical_sha256(self.binding)[:32]
            self.binding["trace_ref"] = self.ref
            self.base = Path("gateway-agent-traces/v1/owners") / owner_ref / operation_ref
            self.secrets = tuple(secrets)
            self.count, self.head, self.size = 0, GENESIS, 0
            self.rejected, self.refusal, self.failure_written = False, None, False
        except Exception:
            raise TraceError() from None

    def _refuse(self, failure_class: str, rule: str | None = None) -> TraceError:
        self.rejected = True
        if self.refusal is None:
            self.refusal = (failure_class, rule)
        return TraceError(failure_class, rule)

    def _checked(self, kind: str, payload) -> tuple[dict, bytes]:
        if kind not in KINDS or type(payload) is not dict:
            raise self._refuse("schema_error")
        try:
            canonical_bytes(payload)
        except Exception:
            raise self._refuse("schema_error") from None
        try:
            _private_value(payload, self.secrets, result=kind == "result")
        except Exception as exc:
            if "out of range" in str(exc):
                raise self._refuse("schema_error") from None
            from .trace_redact import first_credential_rule
            raise self._refuse("credential_refused", first_credential_rule(payload)) from None
        value = {"schema": SCHEMA, **self.binding, "sequence": self.count,
            "kind": kind, "prior_sha256": self.head, "payload": payload}
        value["record_sha256"] = canonical_sha256(value)
        raw = canonical_bytes(value)
        if (len(raw) > MAX_RECORD_BYTES or self.size + len(raw) > REGULAR_BYTES
                or self.count >= REGULAR_RECORDS):
            raise self._refuse("size_bound")
        return value, raw

    def _write(self, value: dict, raw: bytes) -> None:
        with open_artifact_root(self.root, expected=self.identity) as fs:
            # The pinned root/ancestors cannot be swapped during ACL setup.
            with fs.borrow_descriptor() as descriptor:
                if descriptor.fd is not None:
                    os.fchmod(descriptor.fd, 0o700)
                else:
                    _secure_owner_only(self.root, directory=True)
            fs.write_new_or_same(self.base / f"{self.count:08d}.json", raw)
            fs.write_new_or_same(self.base / f"head-{self.count:08d}.json",
                canonical_bytes({"schema": "flywheel.gateway-agent-head/v1",
                    **self.binding, "record_count": self.count + 1,
                    "trace_head_sha256": value["record_sha256"]}))
        self.count += 1
        self.head = value["record_sha256"]
        self.size += len(raw)

    def append(self, kind: str, payload: dict) -> None:
        if self.rejected:
            failure_class, rule = self.refusal or ("custody_error", None)
            raise TraceError(failure_class, rule)
        value, raw = self._checked(kind, payload)
        try:
            self._write(value, raw)
        except Exception:
            raise self._refuse("custody_error") from None

    def append_failure(self, failure_class: str, rule: str | None = None) -> None:
        """The one record accepted past the regular bound, once: class, catalog
        rule id (or None) and the sequence of the refused record."""
        if (self.failure_written or failure_class not in FAILURE_CLASSES
                or rule is not None and (type(rule) is not str or not _RULE.fullmatch(rule))
                or self.count >= MAX_RECORDS):
            raise TraceError("schema_error")
        payload = {"schema": FAILURE_SCHEMA, "class": failure_class, "rule": rule,
                   "sequence": self.count}
        value = {"schema": SCHEMA, **self.binding, "sequence": self.count,
                 "kind": "failure", "prior_sha256": self.head, "payload": payload}
        value["record_sha256"] = canonical_sha256(value)
        raw = canonical_bytes(value)
        if len(raw) > MAX_FAILURE_BYTES or self.size + len(raw) > MAX_TRACE_BYTES:
            raise TraceError("size_bound")
        try:
            self._write(value, raw)
        except Exception:
            raise TraceError("custody_error") from None
        self.failure_written = True

    def read_reference(self, trace_ref: str) -> list[dict]:
        if trace_ref != self.ref:
            raise TraceError()
        return self.read()

    def read(self) -> list[dict]:
        try:
            records, head, size = [], GENESIS, 0
            with open_artifact_root(self.root, expected=self.identity, writable=False) as fs:
                try:
                    names = fs.list_names(self.base, max_entries=MAX_RECORDS * 2 + 16)
                except PrivateArtifactError as exc:
                    if exc.code != "NOT_FOUND": raise
                    names = []
                # Atomic writer temporary files are not committed records.
                committed = sorted(n for n in names if re.fullmatch(r"[0-9]{8}\.json", n))
                if (len(committed) > MAX_RECORDS or committed != [
                        f"{i:08d}.json" for i in range(len(committed))]
                        or sorted(n for n in names if not n.startswith(".")) != sorted(
                            committed + ["head-" + n for n in committed])):
                    raise TraceError()
                for seq in range(len(committed)):
                    raw = fs.read_bytes(self.base / f"{seq:08d}.json", max_bytes=MAX_RECORD_BYTES)
                    size += len(raw)
                    value = strict_load_json(raw, max_bytes=MAX_RECORD_BYTES, max_depth=32)
                    digest = value.pop("record_sha256")
                    if (size > MAX_TRACE_BYTES or seq >= MAX_RECORDS
                            or set(value) != {"schema", *self.binding, "sequence", "kind", "prior_sha256", "payload"}
                            or value["schema"] != SCHEMA or value["sequence"] != seq
                            or value["kind"] not in KINDS or value["prior_sha256"] != head
                            or any(value[k] != v for k, v in self.binding.items())
                            or canonical_sha256(value) != digest):
                        raise TraceError()
                    _private_value(value["payload"], (), result=value["kind"] == "result")
                    value["record_sha256"] = digest
                    checkpoint = strict_load_json(fs.read_bytes(
                        self.base / f"head-{seq:08d}.json", max_bytes=2048))
                    if checkpoint != {"schema": "flywheel.gateway-agent-head/v1",
                            **self.binding, "record_count": seq + 1, "trace_head_sha256": digest}:
                        raise TraceError()
                    records.append(value)
                    head = digest
            self.count, self.head, self.size = len(records), head, size
            return records
        except Exception:
            raise TraceError() from None

    def projection(self, state: str, **kwargs) -> dict:
        return projection(self.binding, state, self.count, self.head, **kwargs)


def record_failure(trace: "AgentTrace", exc: BaseException) -> None:
    """End a failed run's private trace with one failure record (N-12).

    After a refusal the trace accepts only the fixed-schema record in its
    reserved slot; otherwise the diagnostic record is tried first, and a
    refusal of that record falls back to the fixed one. A failure record that
    cannot be written is logged by class, never by value."""
    try:
        if trace.refusal is not None:
            trace.append_failure(*trace.refusal)
            return
        try:
            trace.append("failure", {"error_type": type(exc).__name__, "message": str(exc)})
        except TraceError:
            trace.append_failure(*trace.refusal)
    except TraceError as missed:
        _log.warning("private trace failure record not written (%s)", missed.failure_class)


class TraceLedger(SessionLedger):
    def __init__(self, trace: AgentTrace):
        super().__init__()
        self.trace = trace

    def append(self, kind, content, meta=None):
        entry = super().append(kind, content, meta)
        try:
            self.trace.append("ledger", asdict(entry))
        except Exception:
            self.entries.pop()
            raise
        return entry
