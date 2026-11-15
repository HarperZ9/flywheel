"""Intent-based voice: a spec built from what the writer wants to do, and a
check that scores a draft against it.

build_spec takes a goal, an audience, a stance and optional samples. The words
of the goal and stance choose the moves the draft must make (an anchor, a
turn, a question, a what-if, the other side). Samples set measured ranges and
show which template devices they lean on; the spec keeps the moves and limits
the devices either way, so a spec built from a model-sounding sample still asks
for better writing than the sample.

check runs voice_devices and the line checker, compares each count with the
spec and returns every check with its value, its line and a fix. The score is
the share of checks met, 0 to 100. It measures fit to the spec and says
nothing about whether the claims are true or who wrote the text.

Standard library only. The spec holds aggregates and hashes, never sample text.
"""
import copy
import hashlib
import json
import os
import re

from . import detector
from . import voice_devices as vd
from . import voice_features as vf
from . import voice_register
from .voice_intent_specs import (BUILTIN, DEFAULT_LIMITS, DEFAULT_RANGES, GOAL_WANTS, SCHEMA,
                                 STANCE_WANTS, TELL_WHY, WORK_HOW)

CHECK_SCHEMA = "articulate/voice-intent-check/v1"
SCORE_MEANS = "Share of the spec's checks this draft meets. It does not check facts or authorship."
TOOL = re.compile(r"`[^`\n]+`|\bpip install\b")
# Register features a spec may want; articulate.voice_register counts them.
REGISTER_WANTS = ("imagery", "forward-motion", "observer", "idea-runs", "analogy", "symbol",
                  "confrontation")


def load_spec(ref):
    """A built-in spec by name, or a spec JSON file by path."""
    if ref in BUILTIN:
        return copy.deepcopy(BUILTIN[ref])
    if not os.path.isfile(ref):
        raise ValueError(f"no intent spec {ref!r}: name a file or one of {', '.join(sorted(BUILTIN))}")
    with open(ref, "r", encoding="utf-8") as fh:
        spec = json.load(fh)
    if spec.get("schema") != SCHEMA:
        raise ValueError(f"{ref} is not an intent spec (schema {spec.get('schema')!r})")
    return spec


def _wants_from(text, table):
    low = (text or "").lower()
    return [w for words, wants in table if any(k in low for k in words) for w in wants]


def _sample_stats(samples):
    """Ranges and template-device counts from reference samples, no text kept."""
    measures = [vf.scalars(vf.measure(s)) for s in samples]
    devices = [vd.analyze(s) for s in samples]
    cvs = [m["sentence_len_cv"] for m in measures if m["sentence_len_cv"]]
    tells = {}
    for d in devices:
        for h in d["tells"]:
            tells[h["id"]] = tells.get(h["id"], 0) + 1
    works = {k: sum(d["counts"][k] for d in devices) for k in vd.WORK_LABELS}
    return {"samples": [{"sha256": "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest(),
                         "words": vf.measure(s)["words"]} for s in samples],
            "sentence_len_cv": min(cvs) if cvs else None,
            "one_line_share": max(d["one_line_share"] for d in devices),
            "tells": tells, "works": works}


def build_spec(goal, audience, stance, samples=(), *, base=None, name="custom", tools=()):
    """A spec from intent words, an optional base spec and optional reference samples."""
    spec = load_spec(base) if base else {"schema": SCHEMA, "limits": dict(DEFAULT_LIMITS),
                                          "wants": {}, "ranges": copy.deepcopy(DEFAULT_RANGES),
                                          "traits": [], "sources": {"samples": []}}
    spec["name"] = name
    for key, value in (("goal", goal), ("audience", audience), ("stance", stance)):
        if value:
            spec[key] = value
    for want in _wants_from(spec.get("goal"), GOAL_WANTS) + _wants_from(spec.get("stance"), STANCE_WANTS):
        spec["wants"].setdefault(want, 1)
    if tools:
        spec["tools"] = list(tools)
    if samples:
        stats = _sample_stats(list(samples))
        spec["sources"]["samples"] = stats["samples"]
        spec["sources"]["sample_tells"] = stats["tells"]
        spec["sources"]["sample_works"] = stats["works"]
        if stats["sentence_len_cv"]:
            floor = round(min(stats["sentence_len_cv"], 0.6) * 0.9, 2)
            spec["ranges"]["sentence_len_cv"] = {"min": max(floor, 0.3)}
    spec["plan"] = plan(spec)
    return spec


def plan(spec):
    """The moves in writing order, then what to leave out, as plain sentences."""
    order = ("anchor", "imagery", "observer", "counter-view", "other-shoes", "what-if", "stance",
             "turn", "forward-motion", "idea-runs", "analogy", "symbol", "confrontation", "tool",
             "reader-question")
    steps = [WORK_HOW[w] for w in order if spec.get("wants", {}).get(w)]
    leaning = sorted(spec.get("sources", {}).get("sample_tells", {}).items(), key=lambda kv: -kv[1])
    if leaning:
        names = ", ".join(vd.TELL_LABELS.get(k, k) for k, _ in leaning[:4])
        steps.append(f"Your samples lean on: {names}. Keep what the samples do well and drop these.")
    cut = [k for k, v in spec.get("limits", {}).items() if v == 0]
    if cut:
        steps.append("Leave out: " + "; ".join(TELL_WHY.get(k, k) for k in cut[:6]) + ".")
    return steps


def measure(text, spec=None):
    """Device counts, house-device findings and the ranged scalars for one text."""
    dev = vd.analyze(text)
    house = detector.check_text(text)
    house_hits = [{"id": "house-devices", "line": f["line"], "snippet": f["snippet"][:90],
                   "detail": f["category"]} for f in house["high"] + house["medium"]]
    scal = vf.scalars(vf.measure(text))
    tools = [t.lower() for t in (spec or {}).get("tools", ())]
    tool_hits = [{"id": "tool", "line": n, "snippet": line.strip()[:90], "detail": ""}
                 for n, line in enumerate(text.splitlines(), 1)
                 if TOOL.search(line) or any(t in line.lower() for t in tools)]
    reg = voice_register.measure(text)
    reg_hits = [{"id": k, "line": n, "snippet": "", "detail": ""}
                for k in REGISTER_WANTS for n in reg["lines"][k]]
    counts = dict(dev["counts"], **{"house-devices": len(house_hits), "tool": len(tool_hits)},
                  **{k: reg["counts"][k] for k in REGISTER_WANTS})
    values = {"sentence_len_cv": scal["sentence_len_cv"],
              "one_line_share": dev["one_line_share"]}
    return {"devices": dev, "counts": counts, "values": values,
            "hits": dev["tells"] + dev["works"] + house_hits + tool_hits + reg_hits,
            "register": reg}


def _check(kind, key, bound, value, hits, note):
    ok = value <= bound if kind == "limit" else value >= bound
    mine = [h for h in hits if h["id"] == key]
    return {"id": key, "kind": kind, "bound": bound, "value": value, "ok": ok,
            "lines": sorted({h["line"] for h in mine})[:8], "note": note,
            "examples": [{"line": h["line"], "snippet": h["snippet"], "detail": h.get("detail", "")}
                         for h in mine[:3]]}


def check(text, spec):
    """Every check in the spec against text, the hits behind each and a 0 to 100 score."""
    m = measure(text, spec)
    checks = [_check("limit", k, v, m["counts"].get(k, 0), m["hits"], TELL_WHY.get(k, ""))
              for k, v in spec.get("limits", {}).items()]
    checks += [_check("want", k, v, m["counts"].get(k, 0), m["hits"], WORK_HOW.get(k, ""))
               for k, v in spec.get("wants", {}).items()]
    for key, rng in spec.get("ranges", {}).items():
        value = m["values"].get(key)
        if value is None:
            continue
        if "min" in rng:
            checks.append(_check("want", key, rng["min"], value, [], "vary sentence length"
                                 if key == "sentence_len_cv" else ""))
        if "max" in rng:
            checks.append(_check("limit", key, rng["max"], value, [], ""))
    met = sum(c["ok"] for c in checks)
    return {"schema": CHECK_SCHEMA, "spec": spec.get("name"), "score": round(100 * met / len(checks))
            if checks else 100, "met": met, "total": len(checks), "score_means": SCORE_MEANS,
            "checks": checks, "tells": [h for h in m["hits"] if h["id"] in TELL_WHY],
            "works": [h for h in m["hits"] if h["id"] in WORK_HOW],
            "words": vf.measure(text)["words"]}
