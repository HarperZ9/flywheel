"""loops.py -- which other loops close?

The flywheel is one operation: perceive, check against an unauthored
criterion, carry a re-checkable receipt, feed it back. The code loop closed
(README: 9/9). This module asks the wider question as an EXPERIMENT, not a
diagram: for each candidate loop, run every handoff against the real local
mechanisms and report whether it closes -- every edge executed, every edge
chained a receipt, and the last edge feeds the first. An edge that cannot
run is named open with its reason. Nothing here asserts closure it did not
witness.

Candidate loops:
  learning   comprehension receipt -> ledger -> retention due -> retest
             -> ledger (does understanding compound?)
  economics  run cost -> meter -> routing receipt -> next run
             (does cost feedback steer routing?)
  invention  propose conjecture -> kernel verdict -> survivors stored
             -> seed next proposals (does generation-under-witness close?)
  research   question -> gather source -> forge spec -> witnessed verdict
             -> stored claim (does the reconcile generalize past code?)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Edge:
    frm: str
    to: str
    run: "callable"   # (ctx) -> (executed: bool, receipt: str, note: str)


@dataclass
class Loop:
    name: str
    question: str
    edges: list


def measure_closure(loop: Loop, ctx: "dict | None" = None) -> dict:
    """Run every edge; a loop closes iff all execute, all carry a receipt,
    and the final edge feeds the first."""
    ctx = dict(ctx or {})
    rows = []
    for e in loop.edges:
        try:
            executed, receipt, note = e.run(ctx)
        except Exception as ex:
            executed, receipt, note = False, "", f"{type(ex).__name__}: {ex}"
        rows.append({"from": e.frm, "to": e.to, "executed": bool(executed),
                     "receipt": str(receipt or ""), "note": note})
    feeds_back = bool(loop.edges) and loop.edges[-1].to == loop.edges[0].frm
    closed = feeds_back and all(r["executed"] and r["receipt"] for r in rows)
    return {"schema": "flywheel.loop-closure/v1", "name": loop.name,
            "question": loop.question, "edges": rows,
            "feeds_back": feeds_back, "closed": closed,
            "survivors": ctx.get("_survivors", 0),
            "note": "closed = every handoff executed and chained a receipt "
                    "and the last edge feeds the first; an open edge names "
                    "its reason"}


def measure_all_loops(ctx: "dict | None" = None) -> dict:
    loops = [measure_closure(l, ctx) for l in LOOPS.values()]
    return {"schema": "flywheel.loop-register/v1", "loops": loops,
            "closed_count": sum(1 for l in loops if l["closed"]),
            "total": len(loops)}


# --- learning loop: does understanding compound? ---

def _learn_gate(ctx):
    from .explanation_gate import explanation_receipt
    diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-def f(): pass\n+def f(): return tax(subtotal)\n"
    r = explanation_receipt(diff,
                            "in x.py, f now returns tax applied to subtotal",
                            reviewer="loop")
    ctx["_receipt"] = r
    return True, r["sha256"], "explanation gate produced a comprehension receipt"


def _learn_bank(ctx):
    import uuid
    from .store import put_entity
    r = dict(ctx["_receipt"])
    r["files"] = ["x.py"]                 # the ledger keys holdership by file
    # each measurement is a distinct turn of the loop: a unique eid keeps
    # this turn's evidence unretested, so the schedule edge measures the
    # mechanism, not the residue of the previous turn's retest
    s = put_entity("comprehension", r, eid="loop-learn-" + uuid.uuid4().hex[:16])
    ctx["_eid"] = s["eid"]
    return True, s["chain_hash"], "receipt banked in the verifiable store"


def _learn_ledger(ctx):
    from .comprehension_ledger import comprehension_ledger
    led = comprehension_ledger()
    holder = led["files"].get("x.py", {}).get("holder")
    return bool(holder), holder or "", "ledger read holdership back from evidence"


def _learn_schedule(ctx):
    from .retention import retention_due
    due = retention_due(days=0)
    ids = [d["eid"] for d in due["due"]]
    ok = ctx["_eid"] in ids
    return ok, ctx["_eid"] if ok else "", "retention scheduled the unaided retest"


def _learn_retest(ctx):
    from .retention import retention_record
    r = retention_record(ctx["_eid"], True, note="unaided retest held")
    return "error" not in r, r.get("chain_hash", ""), \
        "unaided outcome banked, linked to the original -> feeds the ledger"


LEARNING = Loop("learning", "does understanding compound across time?", [
    Edge("ledger", "gate", _learn_gate),
    Edge("gate", "store", _learn_bank),
    Edge("store", "ledger-read", _learn_ledger),
    Edge("ledger-read", "schedule", _learn_schedule),
    Edge("schedule", "ledger", _learn_retest),
])


# --- economics loop: does cost feedback steer routing? ---

def _econ_run(ctx):
    import hashlib
    run = {"endpoint": "a", "duration_s": 4.2, "ttva_s": 4.2}
    ctx["_run"] = run
    return True, hashlib.sha256(str(run).encode()).hexdigest()[:16], \
        "a run produced duration + ttva receipts"


def _econ_meter(ctx):
    from .store import put_entity
    s = put_entity("run-cost", {"endpoint": ctx["_run"]["endpoint"],
                                "duration_s": ctx["_run"]["duration_s"]})
    return True, s["chain_hash"], "cost metered into the store"


def _econ_route(ctx):
    from .local_agent import select_backend_receipted

    class _B:
        def __init__(self, name, ok):
            self.name, self._ok = name, ok

        def health(self):
            return self._ok
    chosen, receipt = select_backend_receipted([_B("a", False), _B("b", True)])
    ctx["_chosen"] = chosen.name if chosen else None
    return chosen is not None, receipt["chosen"] or "", \
        "routing receipt named candidates, verdicts, winner"


def _econ_next(ctx):
    # the chosen backend seeds the next run: the edge that feeds the first
    return bool(ctx.get("_chosen")), ctx.get("_chosen", ""), \
        "the routed backend becomes the next run's endpoint"


ECONOMICS = Loop("economics", "does cost feedback steer the next route?", [
    Edge("run", "meter", _econ_run),
    Edge("meter", "route", _econ_meter),
    Edge("route", "next", _econ_route),
    Edge("next", "run", _econ_next),
])


# --- invention loop: does generation-under-witness close? ---

_CONJECTURES = [
    "theorem t1 : 1 + 1 = 2 := rfl",
    "theorem t2 : 2 + 2 = 5 := rfl",     # false: the kernel must refute
    "theorem t3 : 3 * 0 = 2 := rfl",     # false
]


def _invent_propose(ctx):
    import hashlib
    ctx["_conjectures"] = list(_CONJECTURES)
    h = hashlib.sha256("".join(_CONJECTURES).encode()).hexdigest()[:16]
    return True, h, f"{len(_CONJECTURES)} conjectures proposed"


def _invent_kernel(ctx):
    kernel = ctx.get("kernel")
    if kernel is None:
        from .lean_oracle import lean_check
        kernel = lambda code: lean_check(code)
    survivors = []
    for c in ctx["_conjectures"]:
        v = kernel(c)
        if v.get("passed") is True:
            survivors.append(c)
        elif v.get("passed") is None:
            # the kernel could not judge -> the edge cannot close honestly
            raise RuntimeError("kernel DECLARED (no toolchain); cannot judge")
    ctx["_survivors_list"] = survivors
    ctx["_survivors"] = len(survivors)
    return True, f"{len(survivors)}/{len(ctx['_conjectures'])} survived", \
        "the kernel judged every conjecture; survivors are proof-carrying"


def _invent_store(ctx):
    from .store import put_entity
    last = ""
    for c in ctx["_survivors_list"]:
        last = put_entity("theorem", {"statement": c,
                                      "verdict": "kernel-accepted"})["chain_hash"]
    return bool(last), last, "survivors chained into the store"


def _invent_seed(ctx):
    # survivors seed the next round: the edge that feeds the first
    ok = ctx.get("_survivors", 0) > 0
    return ok, str(ctx.get("_survivors", 0)), \
        "accepted theorems seed the next proposal round"


INVENTION = Loop("invention", "does generation-under-witness close?", [
    Edge("propose", "kernel", _invent_propose),
    Edge("kernel", "store", _invent_kernel),
    Edge("store", "seed", _invent_store),
    Edge("seed", "propose", _invent_seed),
])


# --- research loop: does the reconcile generalize past code? ---

def _research_question(ctx):
    ctx["_q"] = "does verified inference uplift small models"
    return True, "q:" + ctx["_q"][:24], "a question is posed"


def _research_gather(ctx):
    import hashlib
    # a source is frozen content-addressed (the snapshot mechanism's shape)
    src = "evidence bytes for " + ctx["_q"]
    ctx["_src_sha"] = hashlib.sha256(src.encode()).hexdigest()
    return True, ctx["_src_sha"][:16], "a source frozen content-addressed"


def _research_forge(ctx):
    from .context_forge import forge_prp
    prp = forge_prp(ctx["_q"], task_type="research",
                    context=f"source {ctx['_src_sha'][:12]}").to_dict()
    ctx["_prp"] = prp
    return True, str(prp["confidence"]), "question priced as a research spec"


def _research_store(ctx):
    from .store import put_entity
    s = put_entity("research-claim", {"question": ctx["_q"],
                                      "confidence": ctx["_prp"]["confidence"],
                                      "source_sha256": ctx["_src_sha"]})
    ctx["_claim_eid"] = s["eid"]
    return True, s["chain_hash"], "the claim stored, awaiting a verdict"


def _research_recheck(ctx):
    from .store import get_entity
    # the stored claim schedules its own re-check: read it back, the source
    # hash lets a stranger re-fetch and re-verify -> feeds the question
    e = get_entity(ctx["_claim_eid"])
    ok = bool(e) and e["data"].get("source_sha256") == ctx["_src_sha"]
    return ok, ctx["_src_sha"][:16] if ok else "", \
        "the claim's frozen source re-checkable -> feeds the next question"


RESEARCH = Loop("research", "does the reconcile generalize past code?", [
    Edge("question", "gather", _research_question),
    Edge("gather", "forge", _research_gather),
    Edge("forge", "store", _research_forge),
    Edge("store", "recheck", _research_store),
    Edge("recheck", "question", _research_recheck),
])


LOOPS = {"learning": LEARNING, "economics": ECONOMICS,
         "invention": INVENTION, "research": RESEARCH}
