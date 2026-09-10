"""Content-free stage sink for explicit proposer and transport observation."""
from __future__ import annotations

import json
import os

from .local_finalizer_accounting import digest, write_new
from .local_usage import ollama_native_usage



class InvocationStage:
    def __init__(self, context, identity):
        self.context, self.identity = context, identity
        self.events, self.receipt = [], None
        self.instrumented = False
        self.transport_observed = False
        self.current_invocation = None
        self.invocations = 0
        self.path = context.root / identity["path"]

    def check(self):
        self.context.check()

    def _append(self, event):
        path = self.path.with_name("invocations.jsonl")
        if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
               for p in (path, *path.parents)):
            raise OSError("unsafe accounting path")
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "x" if not self.events else "a"
        with path.open(mode, encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def emit(self, kind, **fields):
        self.check()
        if self.receipt is not None:
            raise ValueError("stage already finalized")
        event = {"stage_id": self.identity["stage_id"], "seq": len(self.events),
                 "kind": kind, **fields}
        event["event_id"] = digest(event)
        try:
            self._append(event)
        except Exception:
            self.context.fatal()
        self.events.append(event)

    def enter(self):
        self.emit("runner_entered")

    def instrument(self):
        if not self.instrumented:
            self.emit("observation_started")
            self.instrumented = True

    def attach(self, backend):
        self.instrument()
        if self.context.transport_factory is not None:
            from .local_finalizer_transport_accounting import TransportObservation
            backend.transport = TransportObservation(self, self.context.transport_factory)
            self.emit("transport_observation_started")
            self.transport_observed = True

    def started(self, max_output_tokens):
        self.instrument()
        if self.current_invocation is not None:
            raise ValueError("concurrent stage invocation unsupported")
        self.invocations += 1
        identity = digest({"stage_id": self.identity["stage_id"], "ordinal": self.invocations})
        tokens = max_output_tokens if type(max_output_tokens) is int and max_output_tokens >= 0 else None
        self.emit("invocation_started", invocation_id=identity,
                  ordinal=self.invocations, max_output_tokens=tokens)
        self.current_invocation = identity
        return identity

    def finished(self, identity, outcome, usage):
        if identity != self.current_invocation:
            raise ValueError("invocation identity mismatch")
        clean = ollama_native_usage(usage) if isinstance(usage, dict) else None
        self.emit("invocation_terminal", invocation_id=identity, outcome=outcome, usage=clean)
        self.current_invocation = None

    def finish(self, disposition, *, result_state=None, eligible=None, caused_by=None):
        self.check()
        self.emit("stage_disposition", disposition=disposition, result_state=result_state,
                  eligible=eligible, caused_by=caused_by)
        receipt = {"schema": "harness.local-finalizer-invocation-receipt/v1", **self.identity,
                   "disposition": disposition, "events": list(self.events),
                   "events_sha256": digest(self.events)}
        try:
            write_new(self.path, receipt)
        except Exception:
            self.context.fatal()
        self.receipt = receipt
