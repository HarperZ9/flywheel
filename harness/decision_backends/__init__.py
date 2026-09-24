"""Decision backends: the protocol, the registry and the read-result check.

A backend reads one rendered state against a map of typed /v1/systemone
questions and returns, per question, a raw label distribution that includes
the none label. It never receives a target label. The two harness controls
that read labels (label-shuffle and oracle) get them from the suite when they
are built, and declare ``sees_labels`` in their capabilities.

Registry specs accepted by ``resolve``:

- ``controls``: the five harness controls in ``controls.py``;
- ``lexical``: the path and token-overlap rule in ``lexical.py``;
- ``http``: the factory ``harness.decision_backends.http_systemone:create``;
- ``module:<package.module>:<factory>``: imported only when resolved. The
  factory takes no arguments and returns one backend.

``read(state, questions, *, deadline_ms)`` returns, and ``check_read``
enforces::

    {"answers": {qid: {"raw": {label: p, ..., none_label: p},
                       "label_mass": float in (0, 1],
                       "order_agreement": bool}},
     "usage": {"input_tokens": int, "output_tokens": int},
     "reads": int, "gpu_seconds": float | None,
     "weights_sha256": str | None, "cache_path": str | None}

``read_items`` drives a backend over suite items and returns the bench rows,
and ``as_scorer`` puts any backend behind ``score_workflow_batch``. A backend
sees each question under ``question_key(item_id)``, a hash, in key order, so
neither a question id nor the question order can carry a label that a suite
builder encoded in its item ids or its item order. This module
calls no model and no network. A distribution that passes the check is well
formed; nothing here says it is right.
"""
from __future__ import annotations

import hashlib
import importlib
import math
import re
import sys
import time
from typing import Protocol, runtime_checkable

from ..classifier_calibration import ABSTAIN
from ..classifier_workflows import exception_type_name
from ..evidence_json import canonical_sha256
from ..systemone_contract import (
    MAX_QUESTIONS, NONE_LABEL, NOUL_NONE, answer_labels, from_decision_request,
    render_state)

PROB_TOLERANCE = 1e-3
HTTP_FACTORY = "harness.decision_backends.http_systemone:create"
_DOTTED = r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
_MODULE_SPEC = re.compile(rf"module:({_DOTTED}):([A-Za-z_][A-Za-z0-9_]*)\Z")
_REF_CHARS = re.compile(r"[^A-Za-z0-9._:-]")
_OPTIONAL_TEXT = ("weights_sha256", "cache_path")


class BackendResultError(ValueError):
    """A backend returned a result outside the read contract (fixed code)."""


@runtime_checkable
class DecisionBackend(Protocol):
    """Anything with a backend id, capabilities and a read."""

    backend_id: str

    def capabilities(self) -> dict:
        """question_types, max_options, max_state_tokens, shared_state, local,
        deterministic, sees_labels."""

    def read(self, state: str, questions: dict, *, deadline_ms: int) -> dict:
        """Raw per-question label distributions for one state."""


def none_label(question: dict) -> str:
    """The none label a question's distribution carries."""
    return NOUL_NONE if question["type"] == "noul" else NONE_LABEL


def question_key(item_id: str) -> str:
    """The opaque question id a backend sees for one suite item."""
    return "q" + hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:24]


def _factory(module_name: str, attr: str):
    backend = getattr(importlib.import_module(module_name), attr)()
    if not isinstance(backend, DecisionBackend):
        raise ValueError("factory did not return a decision backend")
    return backend


def resolve(spec: str, *, items=None, act_on=(), seed: int = 1709,
            coverage: float = .3) -> list[tuple[str, object]]:
    """Return ``[(arm_name, backend), ...]`` for one registry spec.

    ``items``, ``act_on``, ``seed`` and ``coverage`` reach the controls only.
    """
    if spec == "controls":
        from .controls import make_controls
        return make_controls(items or [], act_on, seed=seed, coverage=coverage)
    if spec == "lexical":
        from .lexical import LexicalBackend
        return [("lexical", LexicalBackend())]
    if spec == "http":
        module_name, _, attr = HTTP_FACTORY.rpartition(":")
        return [("http", _factory(module_name, attr))]
    match = _MODULE_SPEC.fullmatch(spec) if type(spec) is str else None
    if match is None:
        raise ValueError("unknown backend spec")
    return [(spec, _factory(match.group(1), match.group(2)))]


def _fail(code: str) -> None:
    raise BackendResultError(code)


def _finite(value: object, low: float, high: float) -> bool:
    return (type(value) in (int, float) and math.isfinite(value)
            and low <= value <= high)


def _answer(answer: object, question: dict) -> dict:
    if type(answer) is not dict or set(answer) != {"raw", "label_mass", "order_agreement"}:
        _fail("answer_shape")
    labels = answer_labels(question) + [none_label(question)]
    raw = answer["raw"]
    if type(raw) is not dict or not raw or not set(raw) <= set(labels):
        _fail("raw_labels")
    if not all(_finite(v, 0, 1) for v in raw.values()):
        _fail("raw_value")
    total = math.fsum(raw.values())
    if abs(total - 1) > PROB_TOLERANCE:
        _fail("raw_sum")
    if not _finite(answer["label_mass"], 0, 1) or answer["label_mass"] <= 0:
        _fail("label_mass")
    if type(answer["order_agreement"]) is not bool:
        _fail("order_agreement")
    return {"raw": {k: float(raw.get(k, 0.0)) / total for k in labels},
            "label_mass": float(answer["label_mass"]),
            "order_agreement": answer["order_agreement"]}


def check_read(result: object, questions: dict) -> dict:
    """Validate one read result against the questions it answers, fill absent
    labels with zero, renormalize, and return an independent copy."""
    if type(result) is not dict or type(result.get("answers")) is not dict:
        _fail("result_shape")
    if set(result["answers"]) != set(questions):
        _fail("answer_keys")
    usage = result.get("usage", {"input_tokens": 0, "output_tokens": 0})
    if type(usage) is not dict or not all(
            type(usage.get(k)) is int and usage[k] >= 0
            for k in ("input_tokens", "output_tokens")):
        _fail("usage")
    gpu = result.get("gpu_seconds")
    if gpu is not None and not _finite(gpu, 0, math.inf):
        _fail("gpu_seconds")
    reads = result.get("reads", 1)
    if type(reads) is not int or reads < 0:
        _fail("reads")
    if any(type(result.get(k)) not in (str, type(None)) for k in _OPTIONAL_TEXT):
        _fail("provenance")
    return {"answers": {qid: _answer(a, questions[qid])
                        for qid, a in result["answers"].items()},
            "usage": {k: usage[k] for k in ("input_tokens", "output_tokens")},
            "reads": reads, "gpu_seconds": None if gpu is None else float(gpu),
            **{k: result.get(k) for k in _OPTIONAL_TEXT}}


class _Scorer:
    """``score_batch`` over any backend, for ``score_workflow_batch``."""

    def __init__(self, backend, deadline_ms: int):
        self.backend, self.deadline_ms = backend, deadline_ms
        ref = _REF_CHARS.sub("-", str(backend.backend_id))
        self.model_ref = (ref if ref[:1].isalnum() else "b" + ref)[:128]

    def score_batch(self, requests: list, *, task_family: str) -> list[dict]:
        return [self._score(request, task_family) for request in requests]

    def _score(self, request: dict, family: str) -> dict:
        mapped = from_decision_request(request, family)
        ((qid, question),) = mapped["questions"].items()
        read = self.backend.read(render_state(mapped["state"]), {qid: question},
                                 deadline_ms=self.deadline_ms)
        raw = check_read(read, {qid: question})["answers"][qid]["raw"]
        eligible = set(request["eligible_choice_ids"])
        ids = [choice["id"] for choice in request["choices"]]
        rows = [{"choice_id": cid, "eligible": cid in eligible,
                 "probability_like": raw.get(cid, 0.0) if cid in eligible else 0.0}
                for cid in ids]
        rows.append({"choice_id": ABSTAIN, "eligible": True,
                     "probability_like": raw[NONE_LABEL]})
        return {"request_sha256": canonical_sha256(request), "task_family": family,
                "model_ref": self.model_ref, "candidate_ids": ids + [ABSTAIN],
                "scores": rows}


def as_scorer(backend, *, deadline_ms: int = 2000) -> _Scorer:
    """Wrap a backend so any arm plugs into ``score_workflow_batch``. The
    ``__abstain__`` row carries the none mass; results stay shadow there."""
    return _Scorer(backend, deadline_ms)


def _row(item: dict, answer: dict | None, error: str | None) -> dict:
    question = item["question"]
    return {
        "item_id": item["item_id"], "unit_id": item["unit_id"], "split": item["split"],
        "target": item["target"], "tokens": item["tokens"],
        "certification_unit": item["certification_unit"],
        "label_kind": item["label_kind"], "stratum": item.get("stratum"),
        "question_type": question["type"], "labels": answer_labels(question),
        "none_label": none_label(question),
        "input_sha256": canonical_sha256({"state": item["state"], "question": question}),
        "raw": answer["raw"] if answer else None,
        "label_mass": answer["label_mass"] if answer else None,
        "order_agreement": answer["order_agreement"] if answer else None,
        "error_type": None if answer else (error or "backend_unavailable")}


def _read_unit(backend, state, questions, deadline_ms, log, unit_id):
    meta = {"wall_ms": 0.0, "gpu_seconds": 0.0, "input_tokens": 0, "reads": 0,
            "questions": len(questions), "error_type": None, "weights_sha256": None}
    answers, keys, start = {}, list(questions), time.perf_counter()
    try:
        for i in range(0, len(keys), MAX_QUESTIONS):
            chunk = {k: questions[k] for k in keys[i:i + MAX_QUESTIONS]}
            got = check_read(backend.read(state, chunk, deadline_ms=deadline_ms), chunk)
            answers.update(got["answers"])
            meta["weights_sha256"] = got["weights_sha256"]
            meta["reads"] += got["reads"]
            meta["input_tokens"] += got["usage"]["input_tokens"]
            gpu, total = got["gpu_seconds"], meta["gpu_seconds"]
            meta["gpu_seconds"] = None if gpu is None or total is None else total + gpu
    except Exception as exc:  # recorded on the unit and logged; its rows abstain
        # The guarded name: a class built at runtime can carry data in its name.
        meta["error_type"], answers = exception_type_name(exc), {}
        print(f"decision_backends: {backend.backend_id} failed on unit {unit_id}: "
              f"{meta['error_type']}", file=log)
    meta["wall_ms"] = (time.perf_counter() - start) * 1000
    return answers, meta


def _asked(group: list, types: set) -> dict:
    """The unit's readable questions under opaque keys, in key order."""
    keyed = sorted((question_key(i["item_id"]), i["question"]) for i in group
                   if i["question"]["type"] in types)
    if len({k for k, _ in keyed}) != len(keyed):
        raise ValueError("question key collision")
    return dict(keyed)


def read_items(backend, items: list, *, deadline_ms: int = 2000, log=None):
    """Read suite items, one backend call per unit (chunked at the question
    cap), and return ``(rows, units)``. A backend sees each unit's state and
    its questions under opaque keys only, never a target or an item id. A unit
    whose read fails keeps its rows, with ``raw`` None and the exception type
    name as ``error_type``."""
    log = log or sys.stderr
    types = set(backend.capabilities().get("question_types", ()))
    groups: dict = {}
    for item in items:
        groups.setdefault(item["unit_id"], []).append(item)
    rows, units = [], []
    for unit_id, group in groups.items():
        asked = _asked(group, types)
        answers, meta = _read_unit(backend, group[0]["state"], asked, deadline_ms,
                                   log, unit_id)
        units.append({"unit_id": unit_id, **meta})
        for item in group:
            key = question_key(item["item_id"])
            rows.append(_row(item, answers.get(key),
                             "backend_capability" if key not in asked else meta["error_type"]))
    return rows, units
