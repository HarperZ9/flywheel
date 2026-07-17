"""academy_pipeline.py -- the curriculum derived from the code, under
witness.

The pipeline shape (crawl the codebase, identify core abstractions,
order them into a narrative arc, teach one abstraction per chapter)
follows the codebase-to-tutorial approach published by Zachary Huang
(PocketFlow Tutorial-Codebase-Knowledge, MIT), applied here with
attribution and one structural difference: nothing in this curriculum
is narrated beside the code. Each lesson's teach-text IS the live
module docstring, pinned by hash, so documentation rot breaks the
lesson visibly instead of silently. Each lesson names an executable
check against the running gateway, and completion runs through the
receipts that already exist: a teach-back through the explanation gate
banks a comprehension receipt, and retention schedules the unaided
retest. Teaching under witness, like everything else here.
"""
from __future__ import annotations

import hashlib
import importlib

SCHEMA = "flywheel.academy-curriculum/v1"

ATTRIBUTION = ("abstraction-first codebase-to-tutorial shape: Zachary "
               "Huang, PocketFlow Tutorial-Codebase-Knowledge (MIT); "
               "receipt binding: this repository")

COMPLETION_FLOW = ("run the lesson's check against the live gateway, then "
                   "submit a teach-back via POST /api/explain (banks a "
                   "comprehension receipt), then answer the unaided retest "
                   "when GET /api/retention lists it due; held is what "
                   "survives the retest, not what was once shown")

# The arc: foundations first, composition last. One abstraction per
# lesson; prereqs must already have been taught.
CORE_ARC = [
    {"id": "store", "title": "The verifiable substrate",
     "source_module": "harness.store", "prereqs": [],
     "check": {"method": "GET", "path": "/api/store/verify",
               "expect": "ok is true: the audit chain recomputes"}},
    {"id": "envelope", "title": "The proof receipt",
     "source_module": "harness.envelope", "prereqs": ["store"],
     "check": {"method": "GET", "path": "/api/receipts",
               "expect": "a catalog of re-hashed receipt files"}},
    {"id": "oracle", "title": "The external judge",
     "source_module": "harness.oracle", "prereqs": ["envelope"],
     "check": {"method": "GET", "path": "/api/uplift",
               "expect": "every run pins its oracle source hash"}},
    {"id": "admission", "title": "A verifier that can fail",
     "source_module": "harness.task_curator", "prereqs": ["oracle"],
     "check": {"method": "GET", "path": "/api/instruments",
               "expect": "admission_gates present with six gates"}},
    {"id": "loops", "title": "The closed loop, measured",
     "source_module": "harness.loops", "prereqs": ["store", "oracle"],
     "check": {"method": "GET", "path": "/api/loops",
               "expect": "closed_count equals total, every edge receipted"}},
    {"id": "forge", "title": "Generation under witness",
     "source_module": "harness.conjecture_forge",
     "prereqs": ["oracle", "loops"],
     "check": {"method": "POST", "path": "/api/invent",
               "expect": "survivors carry kernel verdicts and rungs"}},
    {"id": "tension", "title": "Disagreement as a receipt",
     "source_module": "harness.tension_ledger", "prereqs": ["envelope"],
     "check": {"method": "GET", "path": "/api/tension",
               "expect": "pairs with frozen sources and earned verdicts"}},
    {"id": "instruments", "title": "The discipline, self-reported",
     "source_module": "harness.eval_engineering",
     "prereqs": ["admission", "loops", "tension"],
     "check": {"method": "GET", "path": "/api/instruments",
               "expect": "every instrument read from its live receipt"}},
]


def _first_paragraph(doc: str) -> str:
    parts = [p.strip() for p in (doc or "").split("\n\n") if p.strip()]
    if not parts:
        return ""
    text = parts[0]
    # a title-only first line is not a lesson; take the body paragraph too
    if len(text) < 60 and len(parts) > 1:
        text = text + " " + parts[1]
    return " ".join(text.split())


def derive_lessons(specs: "list | None" = None) -> list:
    """Derive each lesson from its live source module. A module that
    cannot be imported or has no docstring yields an ABSENT lesson,
    never a fabricated one."""
    out = []
    for s in (CORE_ARC if specs is None else specs):
        teach, sha, present = "", "", False
        try:
            mod = importlib.import_module(s["source_module"])
            doc = mod.__doc__ or ""
            teach = _first_paragraph(doc)
            if teach:
                sha = hashlib.sha256(doc.encode("utf-8")).hexdigest()
                present = True
        except Exception:
            pass
        out.append({"id": s["id"], "title": s["title"],
                    "source_module": s["source_module"],
                    "prereqs": list(s["prereqs"]), "check": dict(s["check"]),
                    "teach": teach, "source_sha256": sha,
                    "present": present})
    return out


def academy_complete(lesson_id: str, comprehension_eid: str) -> dict:
    """Bind a passed comprehension receipt to a lesson, so completion is a
    receipt a stranger can re-check, not prose. The lesson must exist and
    be present, and the referenced receipt must have passed. The binding
    is stored with the lesson's source hash and a relation to the receipt."""
    from .store import get_entity, put_entity, put_relation
    lesson = next((s for s in derive_lessons() if s["id"] == lesson_id), None)
    if lesson is None:
        return {"bound": False, "reason": f"unknown lesson {lesson_id!r}"}
    if not lesson["present"]:
        return {"bound": False, "reason": f"lesson {lesson_id!r} is absent "
                                          "(its source rotted); cannot bind"}
    ent = get_entity(comprehension_eid)
    if ent is None:
        return {"bound": False, "reason": f"no such receipt: "
                                          f"{comprehension_eid}"}
    if ent["data"].get("passed") is not True:
        return {"bound": False, "reason": "the referenced comprehension "
                                          "receipt did not pass"}
    # the receipt must be ABOUT this lesson: its explained files must touch
    # the lesson's source module, or one trivial teach-back would mint
    # completions for every lesson in the curriculum
    module_file = lesson["source_module"].rsplit(".", 1)[-1] + ".py"
    engaged = [str(f).replace("\\", "/")
               for key in ("files", "mentioned_files")
               for f in (ent["data"].get(key) or [])]
    if not any(f == module_file or f.endswith("/" + module_file)
               for f in engaged):
        return {"bound": False,
                "reason": f"receipt does not engage the lesson source "
                          f"({module_file}); a teach-back about an unrelated "
                          f"diff certifies nothing about {lesson_id!r}"}
    doc = {"schema": "flywheel.academy-completion/v1",
           "lesson_id": lesson_id,
           "lesson_source_sha256": lesson["source_sha256"],
           "comprehension_eid": comprehension_eid,
           "comprehension_sha256": ent["sha256"]}
    stored = put_entity("academy-completion", doc)
    put_relation(comprehension_eid, stored.get("eid", ""), "academy-completion")
    return {**doc, "bound": True, "eid": stored.get("eid", ""),
            "chain_hash": stored.get("chain_hash", ""),
            "note": "completion is a receipt bound to the lesson's pinned "
                    "source and a passed comprehension receipt, not prose"}


def academy_curriculum() -> dict:
    lessons = derive_lessons()
    return {"schema": SCHEMA, "lessons": lessons,
            "present_count": sum(1 for l in lessons if l["present"]),
            "total": len(lessons),
            "completion_flow": COMPLETION_FLOW,
            "attribution": ATTRIBUTION,
            "note": "the teach-text is the live module docstring, pinned "
                    "by hash: documentation rot breaks a lesson visibly, "
                    "and a lesson nobody can run is reported absent"}
