"""One editor execution path for the CLI, MCP, and legacy editor entrypoints.

Model assessments are reported as assessments. Local findings and protected-span
checks remain independent, and an unavailable quality score never passes a bar.
"""
from __future__ import annotations

import json
import re

from . import backends, host_edit, prompts, edit_notes


def _scores(output):
    match = re.search(r"\{.*\}", output, re.S)
    try:
        value = json.loads(match.group()) if match else None
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict):
        return None
    if any(type(value.get(k)) is not int or not 1 <= value[k] <= 5
           for k in prompts.QUALITIES):
        return None
    return value


def _strip_preamble(output):
    output = re.sub(r"^\s*```[a-z]*\n", "", output)
    output = re.sub(r"\n```\s*$", "", output)
    lines = output.splitlines()
    if lines and re.match(r"(?i)^(here('?s| is)|sure|below|the rewrite|rewritten)\b.*:$",
                          lines[0].strip()):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines)


def run_edit(text, goal="fix", *, backend=None, mode=None, profile=None,
             is_html=False, is_tex=False, bar=4, passes=3, context="cli",
             sampling=None, sampling_advertised=False, timeout=600,
             allow_change=None, freeze_terms=None):
    """Run an edit, offer a host plan, or return a guarded local fallback.

Every accepted rewrite passes the same stateless submission protocol. Polish
accepts only complete five-score assessments with no individual regression.
"""
    if goal not in ("fix", "polish", "judge"):
        raise ValueError("goal must be fix, polish, or judge")
    if not 1 <= bar <= 5 or passes < 1:
        raise ValueError("bar must be 1-5 and passes must be positive")
    options = dict(mode=mode, profile=profile, is_html=is_html, is_tex=is_tex)
    if allow_change or freeze_terms:
        # Bound in every plan this run makes, so each submit checks the same set.
        options.update(allow_change=allow_change, freeze_terms=freeze_terms)
    plan = host_edit.edit_plan(text, goal=goal, **options)
    attempts, calls, refused = [], [], []
    resolved_profile = plan["profile"]
    ecfg = resolved_profile.get("editor", {}) if isinstance(resolved_profile, dict) else {}
    required = set(ecfg.get("require_fix", []))

    def call(instructions, document):
        output, info = backends.complete(
            prompts.hardened(instructions), document, timeout=timeout,
            backend=backend, context=context, sampling=sampling,
            sampling_advertised=sampling_advertised)
        attempts.extend(info.attempts)
        calls.append({"backend": info.backend, "model": info.model})
        return output, info

    def finish(result, info):
        provenance = {"backend": info.backend, "model": info.model,
                      "attempts": list(attempts)}
        result.update(provenance)
        result["goal"] = goal
        result["model_calls"] = list(calls)
        if "receipt" in result:
            result["receipt"].update(provenance)
            result["receipt"]["model_calls"] = list(calls)
        if refused:
            result["refused"] = refused + result.get("refused", [])
        return edit_notes.annotate_kept(result, text, goal)

    def fallback(info):
        if info.backend == "host":
            result = dict(plan)
            result["next_step"] = (
                "Use these instructions to produce the rewrite or assessment, "
                "then send it with the original text and plan_id to edit_submit.")
        else:
            result = host_edit.deterministic_edit(text, goal=goal, **options)
        if goal == "polish":
            result.update(scores=None, quality_met=False)
        return finish(result, info)

    if goal == "polish" and ecfg and not ecfg.get("run_fix_by_default", True):
        # Preserve authorial/proof modes without spending a model call.
        info = backends.BackendInfo(backend="none", model=None, attempts=[])
        result = host_edit.edit_submit(text, text, plan["plan_id"])
        result.update(scores=None, quality_met=False,
                      note="This mode does not rewrite by default; use judge.")
        return finish(result, info)

    initial_instructions = prompts.quality_instructions() if goal == "polish" else plan["instructions"]
    output, info = call(initial_instructions, plan["masked_text"])
    if info.backend in ("host", "none"):
        return fallback(info)
    if goal == "judge":
        result = host_edit.deterministic_edit(text, goal="judge", **options)
        return finish(host_edit.judge_floor(result, output), info)

    best, best_info = text, info
    baseline = quality = _scores(output) if goal == "polish" else None
    note = ""
    for attempt in range(passes):
        if goal == "polish":
            if quality is None:
                note = "Quality scores unavailable; kept the best checked version."
                break
            current = host_edit.check_under(best, resolved_profile)
            low = {f["category"] for f in current["low"]}
            if (current["gate"] == "ok" and not (required & low)
                    and all(quality[k] >= bar for k in prompts.QUALITIES)):
                break
            candidate_plan = host_edit.edit_plan(best, goal="fix", **options)
            # Quality notes are untrusted model output and use the hardened data block.
            notes = quality.get("worst", [])
            if not isinstance(notes, list):
                notes = []
            notes = [str(n) for n in notes]
            if required & low:
                notes.append("Clear required advisories: " + ", ".join(sorted(required & low)))
            instructions = candidate_plan["instructions"]
            if notes:
                instructions += "\n\n" + prompts._detector_block("Quality suggestions:\n" + "\n".join(notes))
            output, info = call(instructions, candidate_plan["masked_text"])
        else:
            candidate_plan = host_edit.edit_plan(best, goal="fix", **options)
            if attempt:
                output, info = call(candidate_plan["instructions"], candidate_plan["masked_text"])
        if info.backend in ("host", "none"):
            note = "Model unavailable during editing; kept the best checked version."
            break
        if not output.strip():
            note = "Empty rewrite; kept the best checked version."
            break
        candidate = host_edit.edit_submit(best, _strip_preamble(output), candidate_plan["plan_id"],
                                          model=info.model)
        refused.extend(candidate.get("refused", []))
        candidate_text = candidate["text"]
        if goal == "polish":
            score_plan = host_edit.edit_plan(candidate_text, goal="polish", **options)
            score_output, score_info = call(prompts.quality_instructions(), score_plan["masked_text"])
            candidate_quality = _scores(score_output)
            if score_info.backend in ("host", "none") or candidate_quality is None:
                note = "Candidate scores unavailable; kept the best checked version."
                break
            candidate_local = host_edit.check_under(candidate_text, resolved_profile)
            candidate_low = {f["category"] for f in candidate_local["low"]}
            if (any(candidate_quality[k] < quality[k] for k in prompts.QUALITIES)
                    or candidate["gate_after"] != "ok"
                    or required.intersection(candidate_low - low)):
                note = "Candidate regressed a quality score or required advisory, or failed the gate; kept best."
                break
            quality = candidate_quality
        best, best_info = candidate_text, info
        if goal == "fix" and candidate["gate_after"] == "ok":
            break

    scores = {"before": baseline, "after": quality} if baseline and quality else None
    result = host_edit.edit_submit(text, best, plan["plan_id"], scores=scores, model=best_info.model)
    if goal == "polish":
        if result["text"] != best:
            # The final guard can retain different text from the scored candidate.
            # Its scores are then inapplicable, including in the receipt.
            quality = None
            result["quality_status"] = "unassessed_after_guard"
            result["receipt"].update(scores=None, quality_status="unassessed_after_guard")
            note = "Final checks retained different text; quality scores are unavailable for that text."
        local = host_edit.check_under(result["text"], resolved_profile)
        result["scores"] = quality
        result["quality_met"] = bool(quality and result["gate_after"] == "ok"
                                     and not required.intersection(f["category"] for f in local["low"])
                                     and all(quality[k] >= bar for k in prompts.QUALITIES))
    if note:
        result["note"] = note
    return finish(result, best_info)
