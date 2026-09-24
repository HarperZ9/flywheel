"""Wire contract for the decide lane's /v1/systemone request shape.

Validates requests and responses in the public shape plus the optional ``x_flywheel`` block,
renders object and array state as sorted-key JSON, maps one ``flywheel.decision-request/v1``
choice to and from that shape, and renders strict or compatibility answers. Lane limits: 62
read labels per question (A-Z, a-z, 0-9) with the none label (``__none__``, or ``none`` for
noul) taking one, 64 questions, no unknown keys, and 4 characters per token as a pre-check on
the state plus the longest question. Failures raise ``SystemOneError`` (status 422) with a
fixed code that never echoes request content. Nothing here calls a model or proves an answer.
"""
from __future__ import annotations

import copy
import json
import math
import re

from . import decision_contract
from .evidence_json import canonical_bytes, strict_load_json

RECEIPT_SCHEMA = "flywheel.decision-receipt/v1"
NONE_LABEL, NOUL_NONE, NOUL_LABELS = "__none__", "none", ("true", "false")
QUESTION_TYPES = ("noul", "choice", "score")
MODES, SENSITIVITIES = ("shadow", "advise", "act"), ("public", "private")
ABSTAIN_MODES, ACTIONS = ("strict", "compat"), ("act", "abstain")
ABSTAIN_REASONS = (
    "code_gate", "sensitivity_refused", "backend_capability", "format", "order_disagreement",
    "none_top", "invariant_violation", "below_threshold", "set_size_gt_1", "uncalibrated",
    "insufficient_risk_evidence", "infeasible_at_alpha", "revoked", "backend_unavailable",
    "deadline")
ERROR_CODES = ("schema_invalid", "too_many_options", "state_too_long", "unknown_model",
               "label_collision")
MAX_NATIVE_LABELS, MAX_QUESTIONS, MAX_KEY_CHARS = 62, 64, 128
MIN_SCORE_LEVELS, MAX_SCORE_LEVELS, MAX_DEADLINE_MS = 2, 10, 600_000
CHARS_PER_TOKEN, MAX_REQUEST_BYTES, PROB_TOLERANCE = 4, 2 * 1024 * 1024, 1e-3
DEFAULT_MAX_INPUT_CHARS, MAX_INPUT_CHARS_CEILING = CHARS_PER_TOKEN * 8192, CHARS_PER_TOKEN * 32768
DEFAULT_OPTIONS = {
    "task_family": None, "mode": "shadow", "sensitivity": "private", "abstain_mode": "strict",
    "act_on": {}, "none_option": True, "invariants": [], "deadline_ms": 2000}
FAMILY_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAPPED_INSTRUCTIONS = "Choose the option that fits the state."
MAPPED_NONE_DESCRIPTION = "No listed option fits the state."
_DESCRIBED = (str, dict, list)


class SystemOneError(ValueError):
    """A fixed, non-echoing contract failure carrying an HTTP status."""
    def __init__(self, code: str, status: int = 422):
        super().__init__(code)
        self.code, self.status = code, status


def _need(ok: object, code: str = "schema_invalid") -> None:
    if not ok:
        raise SystemOneError(code) from None


def _key(value: object) -> str:
    _need(type(value) is str and 0 < len(value) <= MAX_KEY_CHARS and value.isprintable())
    return value


def _num(value: object, high: float = 1.0) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= high


def _keys(obj: object, required: set, optional: set = frozenset()) -> dict:
    _need(type(obj) is dict and required <= set(obj) <= required | optional)
    return obj


def _snapshot(value: object) -> object:
    try:
        canonical_bytes(value)
    except (ValueError, RecursionError):
        _need(False)
    return copy.deepcopy(value)  # keeps key order: option order is the legend order


def _is_distribution(probs: object, labels=None) -> bool:
    return (type(probs) is dict and bool(probs) and (labels is None or set(probs) == set(labels))
            and all(_num(v) for v in probs.values())
            and abs(sum(probs.values()) - 1.0) <= PROB_TOLERANCE)


def render_state(value: object) -> str:
    """Return string state unchanged and object or array state as sorted-key JSON."""
    if type(value) is str:
        return value
    _need(type(value) in (dict, list))
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def answer_labels(question: dict) -> list[str]:
    """Real answer labels of a validated question, mask applied, none left out."""
    if question["type"] == "noul":
        return list(NOUL_LABELS)
    if question["type"] == "score":
        return [str(i) for i in range(len(question["criteria"]))]
    mask = question.get("x_flywheel", {}).get("eligible")
    return [k for k in question["criteria"] if k != NONE_LABEL and (mask is None or k in mask)]


def read_labels(question: dict, none_option: bool = True) -> list[str]:
    """Labels a backend reads for one question: the real labels, then none."""
    none = NOUL_NONE if question["type"] == "noul" else NONE_LABEL
    declared = question["type"] == "choice" and none in question["criteria"]
    return answer_labels(question) + ([none] if none_option or declared else [])


def _question(q: object, none_option: bool) -> None:
    _keys(q, {"type", "instructions"}, {"criteria", "x_flywheel"})
    kind, crit = q["type"], q.get("criteria")
    _need(kind in QUESTION_TYPES and type(q["instructions"]) is str and q["instructions"]
          and (kind == "noul" or "criteria" in q))
    if kind == "noul":
        _need("criteria" not in q or (type(crit) is dict and set(crit) <= set(NOUL_LABELS)
                                      and all(type(v) in _DESCRIBED for v in crit.values())))
        crit = NOUL_LABELS
    elif kind == "choice":
        _need(type(crit) is dict and any(k != NONE_LABEL for k in crit) and all(
            _key(k) and (v is None or type(v) in _DESCRIBED) for k, v in crit.items()))
        _need(not (none_option and NONE_LABEL in crit), "label_collision")
    else:
        _need(type(crit) is list and len(crit) >= MIN_SCORE_LEVELS
              and all(type(v) in _DESCRIBED for v in crit))
        _need(len(crit) <= MAX_SCORE_LEVELS, "too_many_options")
    _need(len(crit) + int(none_option) <= MAX_NATIVE_LABELS, "too_many_options")
    elig = _keys(q.get("x_flywheel", {"eligible": []}), {"eligible"})["eligible"]
    _need("x_flywheel" not in q or (
        kind == "choice" and type(elig) is list and elig and len(set(map(str, elig))) == len(elig)
        and all(type(e) is str and e in crit and e != NONE_LABEL for e in elig)))


def _options(block: object, questions: dict) -> dict:
    opts = {**DEFAULT_OPTIONS, **_keys(block, set(), set(DEFAULT_OPTIONS))}
    family, deadline, act_on, invariants = (
        opts[k] for k in ("task_family", "deadline_ms", "act_on", "invariants"))
    _need((family is None or (type(family) is str and FAMILY_PATTERN.fullmatch(family)))
          and opts["mode"] in MODES and opts["sensitivity"] in SENSITIVITIES
          and opts["abstain_mode"] in ABSTAIN_MODES and type(deadline) is int
          and 1 <= deadline <= MAX_DEADLINE_MS and type(act_on) is dict
          and type(invariants) is list and len(invariants) <= MAX_QUESTIONS)
    for qid, labels in act_on.items():
        _need(qid in questions and type(labels) is list and labels
              and all(type(x) is str for x in labels) and len(set(labels)) == len(labels)
              and set(labels) <= set(answer_labels(questions[qid])))
    for item in invariants:
        ids = _keys(item, {"kind", "questions"})["questions"]
        _need(item["kind"] == "exclusive" and type(ids) is list and len(ids) >= 2
              and all(type(i) is str and questions.get(i, {}).get("type") == "noul" for i in ids)
              and len(set(ids)) == len(ids))
    return opts


def validate_request(payload: object, *, served_models=None,
                     max_input_chars: int = DEFAULT_MAX_INPUT_CHARS) -> dict:
    """Return an independent validated snapshot of a /v1/systemone request."""
    if not 0 < max_input_chars <= MAX_INPUT_CHARS_CEILING:
        raise ValueError("max_input_chars is outside the backbone ceiling")
    _keys(payload, {"model", "state", "questions"}, {"x_flywheel"})
    snap = _snapshot(payload)
    model, questions, block = _key(snap["model"]), snap["questions"], snap.get("x_flywheel", {})
    none_option = block.get("none_option", True) if type(block) is dict else None
    _need(type(none_option) is bool and type(questions) is dict
          and 0 < len(questions) <= MAX_QUESTIONS)
    for qid, question in questions.items():
        _question(question, none_option if _key(qid) else True)
    family = _options(block, questions)["task_family"]
    _need(not (family and model.startswith("auto:") and model != "auto:" + family))
    longest = max(len(q["instructions"]) + len(render_state(q.get("criteria", "")))
                  for q in questions.values())
    _need(len(render_state(snap["state"])) + longest <= max_input_chars, "state_too_long")
    _need(served_models is None or model in served_models, "unknown_model")
    return snap


def parse_request(raw: bytes | str, **kwargs) -> dict:
    """Strictly parse request bytes (no duplicate keys, no NaN), then validate."""
    try:
        payload = strict_load_json(raw, max_bytes=MAX_REQUEST_BYTES)
    except (ValueError, TypeError):
        payload = None
    return validate_request(payload, **kwargs)


def _answer(ans: object, q: dict | None) -> None:
    kind = ans.get("type") if type(ans) is dict else None
    _need(kind in QUESTION_TYPES and (q is None or q["type"] == kind))
    _keys(ans, {"type", kind} | ({"legend"} if kind == "score" else set())
          | ({"probabilities", "confidence"} if kind != "noul" else set()))
    value, labels = ans[kind], None if q is None else answer_labels(q)
    if kind == "noul":
        return _need(value is None or _num(value))
    if kind == "score":
        legend = ans["legend"]
        _need(type(legend) is list and MIN_SCORE_LEVELS <= len(legend) <= MAX_SCORE_LEVELS
              and all(type(v) in _DESCRIBED for v in legend)
              and (q is None or legend == q["criteria"]))
        labels = [str(i) for i in range(len(legend))]
    probs = ans["probabilities"]
    _need(_is_distribution(probs, labels) and _num(ans["confidence"]) and (
        value is None or (kind == "choice" and type(value) is str and value in probs)
        or (kind == "score" and _num(value, len(labels) - 1))))


def validate_response(payload: object, request: dict | None = None) -> dict:
    """Validated response snapshot; with ``request``, answers match it and strict nulls hold."""
    _keys(payload, {"model", "answers", "usage"}, {"x_flywheel"})
    snap = _snapshot(payload)
    usage, answers = snap["usage"], snap["answers"]
    questions = None if request is None else request["questions"]
    _need(_key(snap["model"]) and type(answers) is dict and answers
          and _keys(usage, {"input_tokens", "output_tokens"})
          and all(type(v) is int and v >= 0 for v in usage.values())
          and (questions is None or set(answers) == set(questions)))
    for qid, ans in answers.items():
        _answer(ans, None if questions is None else questions[_key(qid)])
    block = _keys(snap.get("x_flywheel", {}), set(),
                  {"decisions", "policy_card_sha256", "certification", "receipt"})
    strict = request is not None and request.get("x_flywheel", {}).get(
        "abstain_mode", DEFAULT_OPTIONS["abstain_mode"]) == "strict"
    decisions = block.get("decisions", {})
    _need(type(decisions) is dict and set(decisions) <= set(answers))
    for qid, dec in decisions.items():
        abstained = type(dec) is dict and dec.get("action") == "abstain"
        _need(type(dec) is dict and dec.get("action") in ACTIONS
              and dec.get("reason") in (ABSTAIN_REASONS if abstained else (None,))
              and all(dec.get(k) is None or _num(dec[k])
                      for k in ("p_none", "correct_prob", "label_mass"))
              and (dec.get("raw") is None or _is_distribution(dec["raw"]))
              and type(dec.get("order_agreement")) in (bool, type(None)))
        _need(not (strict and abstained) or answers[qid][answers[qid]["type"]] is None)
    card, receipt = block.get("policy_card_sha256"), block.get("receipt")
    _need((card is None or (type(card) is str and HEX64.fullmatch(card)))
          and type(block.get("certification")) in (dict, type(None))
          and (receipt is None or (
              type(receipt) is dict and receipt.get("schema") == RECEIPT_SCHEMA
              and HEX64.fullmatch(str(receipt.get("request_sha256")))
              and type(receipt.get("does_not_prove")) is str and receipt["does_not_prove"])))
    return snap


def render_answer(question: dict, raw: dict, decision: dict,
                  abstain_mode: str = "strict") -> dict:
    """Render one public-shape answer from a raw read over the real labels plus none.

    Strict mode nulls the value on abstention; compat mode keeps the argmax. All mass on none
    leaves no argmax, so the value is null and the probabilities uniform. ``confidence`` is
    (n*max_p - 1)/(n - 1), the public statistic, and never gates anything."""
    labels, kind = answer_labels(question), question["type"]
    if (abstain_mode not in ABSTAIN_MODES or decision.get("action") not in ACTIONS
            or not _is_distribution(raw) or not set(raw) <= set(read_labels(question))):
        raise ValueError("invalid abstain mode, decision or raw distribution")
    mass = sum(raw.get(k, 0) for k in labels)
    probs = {k: raw.get(k, 0) / mass if mass else 1 / len(labels) for k in labels}
    hide = not mass or (decision["action"] == "abstain" and abstain_mode == "strict")
    if kind == "noul":
        return {"type": kind, "noul": None if hide else round(probs["true"], 6)}
    n, top = len(probs), max(probs.values())
    out = {"type": kind, "probabilities": {k: round(p, 6) for k, p in probs.items()},
           "confidence": round(min(1.0, max(0.0, (n * top - 1) / (n - 1))), 6) if n > 1 else 1.0}
    if kind == "choice":
        return {**out, "choice": None if hide else max(labels, key=probs.get)}
    score = round(sum(int(k) * p for k, p in probs.items()), 6)
    return {**out, "score": None if hide else score, "legend": copy.deepcopy(question["criteria"])}


def to_proposal(answer: dict, decision: dict, *, evidence_refs=()) -> str:
    """Map a choice answer and decision to proposal JSON; only an act on a real option selects."""
    if (type(answer) is not dict or answer.get("type") != "choice"
            or decision.get("action") not in ACTIONS):
        raise ValueError("to_proposal needs a choice answer and a decision")
    acts = decision["action"] == "act" and answer.get("choice") != NONE_LABEL
    return json.dumps({"choice_id": answer.get("choice") if acts else None,
                       "evidence_refs": list(evidence_refs)}, separators=(",", ":"))


def from_decision_request(req: dict, family: str, *, mode: str = "shadow",
                          sensitivity: str = "private") -> dict:
    """Map a decision-request/v1 to one choice question over its eligible ids plus ``__none__``.

    Ineligible choices never reach the model. A malformed request raises the contract's own
    error; an empty eligible set leaves nothing to read and fails with ``schema_invalid``.
    """
    snap = decision_contract.validate_request(req)
    eligible = set(snap["eligible_choice_ids"])
    criteria = {c["id"]: c["description"] for c in snap["choices"] if c["id"] in eligible}
    _need(criteria)
    qid, criteria[NONE_LABEL] = snap["decision_ref"], MAPPED_NONE_DESCRIPTION
    return validate_request({
        "model": f"auto:{family}", "state": snap["state"],
        "questions": {qid: {"type": "choice", "criteria": criteria,
                            "instructions": MAPPED_INSTRUCTIONS}},
        "x_flywheel": {"task_family": family, "mode": mode, "sensitivity": sensitivity,
                       "abstain_mode": "strict", "none_option": False,
                       "act_on": {qid: [k for k in criteria if k != NONE_LABEL]}}})
