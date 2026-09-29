"""Builders for the three Control Tower monitor shapes, as its writers emit them.

Every builder follows control-tower@1cc91b7:
- eval2: protocols/eval2/monitoring/monitor.py (score_all, summary) and
  posthoc.py. The header carries eval.task_registry_name; the value is a
  "<monitor>/<action>" mapping; metadata.scores entries count draws from 1.
- current eval1: eval_logs/monitor_scores.py and trajectories/monitor_score.py.
  Key monitor_<name>; value maps action index to a number or null;
  metadata.action_scores holds Inspect Score dumps or null; NOANSWER is "N".
- legacy eval1: a {max, action_<i>, trajectory} fold under monitor_<name>.

An earlier fixture set used a scalar eval2 value, draw 0, bare numbers in
action_scores and a top-level null. Control Tower writes none of those, so the
controls built on them exercised shapes that do not exist upstream.
"""
import json

EVAL2_TASK = "control_tower/control_eval2"


def raw(value):
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def log(samples, *, eval2):
    header = {"task": "task", "model": "model", "run_id": "run"}
    if eval2:
        header["task_registry_name"] = EVAL2_TASK
    return raw({
        "version": 2,
        "status": "success",
        "eval": header,
        "results": {"total_samples": len(samples), "completed_samples": len(samples)},
        "samples": samples,
    })


def eval2_entry(action, value, *, monitor="strong", draw=1, message_id=None,
                explanation=None):
    return {"action": action, "message_id": message_id or f"m{action}",
            "monitor": monitor, "draw": draw, "value": value,
            "explanation": explanation or "", "prompt": "p", "model": "m"}


def eval2_score(entries, *, mapping=None, monitor="strong"):
    """A score whose mapping is derived the way summary() derives it.

    Pass `mapping` to state it by hand, for drafts or deliberate disagreement.
    """
    if mapping is None:
        mapping = {}
        for e in entries:
            target = "trajectory" if e["action"] is None else e["action"]
            value = e["value"]
            ok = type(value) in (int, float)
            mapping[f"{e['monitor']}/{target}"] = value if ok else "unscored"
    return {"value": mapping, "metadata": {"scores": entries}}


def eval2_sample(sample_id, values, *, extra_scores=None, messages=True):
    entries = [eval2_entry(i, v) for i, v in enumerate(values)]
    sample = {"id": sample_id, "epoch": 1,
              "scores": {"monitor": eval2_score(entries), "task_success": {"value": 1}}}
    if messages:
        sample["messages"] = [{"id": f"m{i}", "role": "assistant"} for i in range(len(values))]
    sample["scores"].update(extra_scores or {})
    return sample


def dump(value, **metadata):
    """An Inspect Score.model_dump() as action_scores holds it."""
    return {"value": value, "explanation": "", "metadata": dict({"monitor_name": "strong"}, **metadata)}


def eval1_score(dumps, *, mapping=None):
    if mapping is None:
        mapping = {}
        for i, d in enumerate(dumps):
            usable = d is not None and type(d["value"]) in (int, float) and not d["metadata"].get("error")
            mapping[str(i)] = d["value"] if usable else None
    return {"value": mapping, "metadata": {"action_scores": dumps}}


def sample(sample_id, scores):
    return {"id": sample_id, "epoch": 1, "scores": scores}
