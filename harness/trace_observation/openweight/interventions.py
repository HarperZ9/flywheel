"""interventions.py -- the per-item arms for reasoning-edit sensitivity (component O2).

Multiple-choice arms, read from option logprobs (round-2 pre-registration):

  FULL            full sampled trace (seed base+1); item excluded if it hit the budget
  FULL_REPEAT     same span read again (readout determinism)
  T2_FULL         second independent trace (seed base+2): the trace-resample baseline,
                  which covers pipeline noise, not only answer-step noise (critic)
  TRUNC_0         empty span (the null; filler is never the null)
  TRUNC_25/50/75  sentence-snapped cuts
  PREFIX_CLOSED   unedited prefix ending at the edit line
  ERROR_CLOSED    same prefix with one literal changed
  NEUTRAL_CLOSED  same prefix with one extra space before that literal
  CONT_A, CONT_B  prefix continued twice (seeds base+3, base+4): the continuation baseline
  ERROR_CONT      error prefix continued (seed base+3)
  FILLER          disruption probe, reported beside TRUNC_0 only when asked for

Code arms: FULL, TRUNC_0, TRUNC_50, MASK_FULL and MASK_50, each answered twice
(s1 selects dependent items, s2 tests them, so selection noise does not carry
into the test). Scoring is injected; run model-written code only in a sandbox.
"""
from __future__ import annotations

from .edits import char_cut, error_edit, filler, mask_code, truncate_fraction

FRACTIONS = (0.25, 0.5, 0.75)


def mc_item(backend, head: str, base_seed: int, *, budget: int = 8192,
            with_filler: bool = False) -> dict:
    t1 = backend.span(head, base_seed + 1, budget, logprobs=True)
    if t1["budget_hit"]:
        return {"status": "excluded_budget"}
    text, tokens = t1["text"], t1["tokens"]
    out = {"status": "ok", "arms": {}, "noop_error": False}
    arms = out["arms"]
    arms["FULL"] = backend.readout(head, text)
    arms["FULL_REPEAT"] = backend.readout(head, text)
    t2 = backend.span(head, base_seed + 2, budget)
    arms["T2_FULL"] = backend.readout(head, t2["text"]) if not t2["budget_hit"] else {"status": "excluded_budget"}
    arms["TRUNC_0"] = backend.readout(head, "")
    for frac in FRACTIONS:
        arms[f"TRUNC_{int(frac * 100)}"] = backend.readout(head, truncate_fraction(text, frac, tokens))
    edit = error_edit(text, char_cut(text, tokens, 0.5))
    if edit["prefix"] is None:
        out["noop_error"] = True
    else:
        arms["PREFIX_CLOSED"] = backend.readout(head, edit["prefix"])
        arms["ERROR_CLOSED"] = backend.readout(head, edit["error"])
        arms["NEUTRAL_CLOSED"] = backend.readout(head, edit["neutral"])
        for name, prefix, seed in (("CONT_A", edit["prefix"], base_seed + 3),
                                   ("CONT_B", edit["prefix"], base_seed + 4),
                                   ("ERROR_CONT", edit["error"], base_seed + 3)):
            cont = backend.span(head + prefix, seed, budget)
            arms[name] = backend.readout(head, prefix + cont["text"])
            arms[name]["budget_hit"] = cont["budget_hit"]
    if with_filler:
        arms["FILLER"] = backend.readout(head, filler(text, tokens))
    out["record"] = t1["record"]
    return out


def code_item(backend, head: str, base_seed: int, score, *, budget: int = 12288,
              answer_seed: int = 300000) -> dict:
    """score(answer_text) -> bool, run by the caller in a sandbox."""
    t = backend.span(head, base_seed + 1, budget)
    if t["budget_hit"]:
        return {"status": "excluded_budget"}
    text = t["text"]
    masked = mask_code(text)
    spans = {"FULL": text, "TRUNC_0": "", "TRUNC_50": truncate_fraction(text, 0.5),
             "MASK_FULL": masked, "MASK_50": truncate_fraction(masked, 0.5)}
    arms = {}
    for name, span in spans.items():
        for s in (1, 2):
            arms[f"{name}_s{s}"] = bool(score(backend.answer(head, span, answer_seed + s)))
    return {"status": "ok", "arms": arms, "record": t["record"]}
