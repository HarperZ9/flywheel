"""Explicit, opt-in experiment accounting. No provider or oracle decisions."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path


class AccountingDurabilityError(RuntimeError):
    """Sticky failure: no subsequent generation may be dispatched."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def write_new(path, value):
    path = Path(path)
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
           for p in (path, *path.parents)):
        raise OSError("unsafe accounting path")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":"), allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


class ExperimentAccounting:
    def __init__(self, *, source_head="unknown", transport_factory=None, bindings=None):
        self.source_head, self.transport_factory = source_head, transport_factory
        rules = {"fixture_source_head": 40, "execution_source_head": 40,
                 "task_set_sha256": 64, "contract_sha256": 64, "profile_sha256": 64,
                 "profile_id": "label", "model_ref": "label",
                 "fixture_source_dirty": "bool", "execution_source_dirty": "bool"}
        self.bindings = {}
        for key, rule in rules.items():
            value = (bindings or {}).get(key)
            valid = (type(value) is bool if rule == "bool" else
                     isinstance(value, str) and re.fullmatch(
                         r"[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,159}" if rule == "label" else rf"[a-f0-9]{{{rule}}}", value))
            self.bindings[key] = value if valid else None
        self.failed = False
        self.manifest = None
        self._stages = {}

    def check(self):
        if self.failed:
            raise AccountingDurabilityError("accounting_durability_failed")

    def fatal(self):
        self.failed = True
        raise AccountingDurabilityError("accounting_durability_failed") from None

    def prepare(self, root, tasks, params, order_hash):
        from .local_finalizer_invocations import InvocationStage
        self.check()
        if self.manifest is not None:
            raise ValueError("accounting context already prepared")
        names = [t["task_id"] for t in tasks]
        if (any(not isinstance(n, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,159}", n)
                for n in names) or len({n.casefold() for n in names}) != len(names)):
            raise ValueError("unsafe or duplicate task identity")
        if params.get("repetitions", 1) != 1:
            raise ValueError("accounting supports one repetition")
        run_id = str(uuid.uuid4())
        planned = []
        for task in tasks:
            prefix_id = digest({"domain": "local-finalizer-prefix/v1", "run_id": run_id,
                "task_set_id": task.get("task_set_id", ""), "task_id": task["task_id"],
                "instance": 0, "prompt": task.get("raw_prompt_sha256", ""),
                "inputs": task.get("visible_input_sha256s", {}),
                "provider_role": params.get("provider_role")})
            for kind in ("normal", "A", "B"):
                folder = "candidate-prefix" if kind == "normal" else kind
                row = {"run_id": run_id, "prefix_id": prefix_id, "task_id": task["task_id"],
                       "stage": kind, "stage_id": digest({"prefix": prefix_id, "stage": kind}),
                       "path": f"{task['task_id']}/{folder}/invocation-receipt.json"}
                planned.append(row)
        self.root = Path(root)
        self.manifest = {"schema": "harness.local-finalizer-accounting-manifest/v1",
            "run_id": run_id, "source_head": self.source_head,
            "source_head_basis": "caller_supplied_revision_not_executed_source_closure",
            "bindings": dict(self.bindings),
            "params_sha256": digest(params), "task_arm_order_sha256": order_hash,
            "stages": planned, "C": "no_finalizer_shared_prefix"}
        try:
            write_new(self.root / "accounting-manifest.json", self.manifest)
        except Exception:
            self.fatal()
        for row in planned:
            self._stages[(row["task_id"], row["stage"])] = InvocationStage(self, row)

    def stage(self, task_id, kind):
        self.check()
        return self._stages[(task_id, kind)]

    def dispatch(self, task_id, kind, callback, *args):
        stage = self.stage(task_id, kind)
        stage.enter()
        try:
            result = callback(*args)
        except BaseException:
            self.check()  # normalized recorder errors cannot clear the fence
            stage.finish("raised")
            raise
        self.check()
        state = result.get("state", "unknown") if isinstance(result, dict) else "unknown"
        state = state if isinstance(state, str) and re.fullmatch(r"[A-Za-z0-9_]{1,80}", state) else "unknown"
        eligible = result.get("eligible", True) if isinstance(result, dict) else None
        stage.finish("returned", result_state=state, eligible=eligible if type(eligible) is bool else None)
        return result

    def skip(self, task_id, kind, reason):
        if kind != "C":
            cause = self.stage(task_id, "normal")
            if reason == "skipped_systemic_arm_block":
                matches = [s for (name, arm), s in self._stages.items()
                           if name != task_id and arm == kind and s.receipt is not None
                           and s.receipt["disposition"] in {"returned", "raised"}]
                if not matches:
                    raise ValueError("systemic skip lacks causal stage")
                cause = matches[-1]
            self.stage(task_id, kind).finish(reason, caused_by=cause.identity["stage_id"])

    def receipts(self):
        return [s.receipt for s in self._stages.values() if s.receipt is not None]

    def finalize(self):
        from .local_finalizer_accounting_verify import aggregate_accounting
        self.check()
        # Re-read exactly manifest-named receipts, not arbitrary nearby files.
        receipts = []
        for row in self.manifest["stages"]:
            path = self.root / row["path"]
            if path.exists():
                if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                       for p in (path, *path.parents)):
                    raise ValueError("unsafe accounting receipt")
                receipt = json.loads(path.read_text(encoding="utf-8"))
                event_path = path.with_name("invocations.jsonl")
                if event_path.is_symlink():
                    raise ValueError("unsafe accounting events")
                events = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()]
                if events != receipt["events"]:
                    raise ValueError("durable event stream differs from receipt")
                receipts.append(receipt)
        result = aggregate_accounting(self.manifest, receipts)
        try:
            write_new(self.root / "invocation-accounting.json", result)
        except Exception:
            self.fatal()
        return result

    def annotate(self, row):
        stage = self.stage(row["task_id"], "normal")
        row["prefix_id"] = stage.identity["prefix_id"]
        row["prefix_receipt_sha256"] = digest(stage.receipt) if stage.receipt else None
        row["legacy_model_calls_after_prefix_basis"] = "finalizer_runner_entries_not_generation"
        if row["arm"] != "C":
            receipt = self.stage(row["task_id"], row["arm"]).receipt
            row["finalizer_receipt_sha256"] = digest(receipt) if receipt else None
