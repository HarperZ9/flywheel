"""Original synthetic diagnostic corpus for classifier data plumbing."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.classifier_dataset import build_split_manifest


VERSION = "classifier-synthetic-v1"
FAMILIES = ("routing", "tool_selection", "context_relevance", "escalation")
SPLITS = ("train", "calibration", "test")
PER_CASE_BY_SPLIT = {"train": 3, "calibration": 2, "test": 2}
DOES_NOT_PROVE = [
    "diagnostic-only synthetic corpus; not production training data",
    "label optimality, independent ground truth, or measured workflow success",
    "authorization, deterministic accept-path bypass, calibration, or deployment readiness",
]

STATE_FORMS = {
    "train": (
        "{actor} asks to {need}. {constraint}",
        "{actor} says {alt_need}. The instruction also says {negation}.",
        "{actor} needs {outcome}; {boundary}",
    ),
    "calibration": (
        "{actor} wants {need}, but {negation}. {boundary}",
        "Task note: {outcome}. {constraint}",
    ),
    "test": (
        "{actor} asks for {alt_need}. {boundary}",
        "A handoff says {need}. {constraint} Also, {negation}.",
    ),
}

ROLE_DESCRIPTIONS = {
    "routing": {
        "local_route": "Use the local Flywheel route with current workspace evidence.",
        "hosted_route": "Use a hosted model route after normal authorization remains intact.",
        "ask_operator": "Ask the operator because authority or intent is missing.",
        "root_coordination": "Escalate routing to root coordination because ownership is shared.",
    },
    "tool_selection": {
        "file_read": "Perform a file read on an identified workspace path.",
        "repo_search": "Search the local repository for matching code or receipts.",
        "math_compute": "Run deterministic math for a bounded calculation.",
        "structured_parse": "Parse structured JSON and validate required fields.",
        "test_run": "Run a focused test run for the touched behavior.",
        "no_call": "Make no tool call because the answer should be produced directly.",
    },
    "context_relevance": {
        "use_pinned": "Use pinned evidence that is directly named in the request.",
        "use_recovery": "Use the recovery note when it matches the active objective.",
        "ignore_irrelevant": "Ignore irrelevant span material that does not affect the decision.",
        "flag_stale": "Flag a stale conflict before treating the memory as current.",
        "ask_missing": "Ask for missing context because the available spans do not decide it.",
    },
    "escalation": {
        "continue": "Continue autonomously within already granted reversible scope.",
        "ask_user": "Ask the user because the next step depends on preference or missing authority.",
        "approval_review": "Escalate for approval review before an external or irreversible action.",
        "root_escalation": "Escalate to root coordination because ownership is shared.",
    },
}

CASES = {
    "routing": {
        "local": (("local_route",), dict(actor="The maintainer", need="inspect a local worktree and run existing checks", alt_need="keep the work inside the repository and avoid provider calls", outcome="a reversible code-read and test path", constraint="No external service or new authority is needed.", negation="do not use a hosted provider for this", boundary="the local harness has the needed files and receipts.")),
        "hosted": (("hosted_route",), dict(actor="The researcher", need="compare a prompt against a hosted endpoint after approval", alt_need="use the configured hosted model route for an advisory score", outcome="a provider-backed comparison with ordinary authorization preserved", constraint="The task depends on an endpoint capability that is not local.", negation="do not let the advisory score bypass approval", boundary="the hosted route is only an advisory input.")),
        "ask": (("ask_operator",), dict(actor="The operator", need="choose between two incompatible goals before work starts", alt_need="clarify whether speed or auditability matters more", outcome="a question back to the operator", constraint="The request omits the preference that decides the route.", negation="do not infer the missing preference", boundary="routing should wait for a user answer.")),
        "coordinate": (("root_coordination",), dict(actor="A peer worker", need="touch files next to another active owner", alt_need="avoid a collision with root-owned training work", outcome="root coordination before route selection", constraint="Ownership is shared across adjacent files.", negation="do not route independently into the same surface", boundary="coordination is the useful next route.")),
        "none": ((), dict(actor="The note", need="publish a model card and charge a customer today", alt_need="claim production adoption without receipts", outcome="none of the listed routing choices fits safely", constraint="No offered routing choice is safe because evidence and authority are missing.", negation="no offered route should be picked just to avoid uncertainty", boundary="no offered routing choice is safe.")),
    },
    "tool_selection": {
        "file_read": (("file_read",), dict(actor="The developer", need="open a named Python file and inspect the validator", alt_need="read the existing spec before editing", outcome="a file read on a local path", constraint="The answer depends on bytes already in the workspace.", negation="do not search the web for this local fact", boundary="reading the file is sufficient.")),
        "search": (("repo_search",), dict(actor="The reviewer", need="find every caller of a route helper", alt_need="locate matching tests and implementation sites", outcome="a repository search over symbols", constraint="The relevant material is spread across files.", negation="do not guess the call graph", boundary="local search is the useful tool.")),
        "math": (("math_compute",), dict(actor="The analyst", need="compute coverage from given counts", alt_need="calculate an error rate from provided integers", outcome="a deterministic math calculation", constraint="All numbers are supplied in the request.", negation="do not run a model for arithmetic", boundary="bounded computation answers it.")),
        "structured_parse": (("structured_parse",), dict(actor="The integrator", need="parse a JSON manifest and check required keys", alt_need="validate structured fields from a saved receipt", outcome="structured parse and field validation", constraint="The input is machine-readable JSON.", negation="do not summarize before validating fields", boundary="parsing decides the next step.")),
        "test_run": (("test_run",), dict(actor="The engineer", need="run one focused test for the changed module", alt_need="verify a regression after a small fix", outcome="a focused test run", constraint="The change has an executable unit check.", negation="do not broaden to unrelated suites first", boundary="the touched behavior needs test evidence.")),
        "no_call": (("no_call",), dict(actor="The user", need="explain the difference between two already provided options", alt_need="answer from the text in the prompt", outcome="no tool call before responding", constraint="The request is answerable without reading, searching, or executing.", negation="do not call tools only to appear busy", boundary="a direct response is the useful action.")),
        "none": ((), dict(actor="The message", need="send an email through an unavailable connector", alt_need="book an external service not represented in the choices", outcome="none of the offered tools applies", constraint="The required external action is outside this tool contract.", negation="outside this tool contract, do not map the request onto a nearby local tool", boundary="no offered tool is acceptable.")),
    },
    "context_relevance": {
        "pinned": (("use_pinned",), dict(actor="The handoff", need="follow pinned evidence from the current spec", alt_need="prefer a receipt explicitly attached to this task", outcome="pinned evidence used as the deciding context", constraint="The pinned evidence names the active file.", negation="do not let loose notes override the pin", boundary="the cited pin is directly relevant.")),
        "recovery": (("use_recovery",), dict(actor="The resumed task", need="apply a recovery note after compaction", alt_need="continue from a saved summary that matches the current files", outcome="a recovery note used for continuity", constraint="The recovery note describes the same objective.", negation="do not restart from an older plan", boundary="the recovery note is relevant context.")),
        "irrelevant": (("ignore_irrelevant",), dict(actor="The packet", need="discard an unrelated project span", alt_need="separate local classifier work from a design note", outcome="irrelevant span material ignored", constraint="The span concerns a different repository.", negation="do not treat nearby text as relevant evidence", boundary="irrelevance is the safe relevance label.")),
        "stale": (("flag_stale",), dict(actor="The memory", need="handle a stale conflict against current files", alt_need="notice that an older note contradicts the worktree", outcome="a stale conflict flagged before use", constraint="Current command output disagrees with the remembered claim.", negation="do not present the stale note as current", boundary="the conflict must be surfaced.")),
        "negation": (("ask_missing",), dict(actor="The instruction", need="respect a negation that blocks the older route", alt_need="resolve whether a past permission still applies", outcome="missing context requested because the negation changes scope", constraint="The available spans do not settle authority.", negation="do not apply the older instruction blindly", boundary="asking is the relevant context action.")),
        "none": ((), dict(actor="The excerpt", need="decide from unrelated background prose", alt_need="use a span with no applicable connection to the request", outcome="no applicable context span", constraint="None of the provided context answers the decision.", negation="none of the available spans should be forced into relevance", boundary="no applicable context is available.")),
    },
    "escalation": {
        "continue": (("continue",), dict(actor="The worker", need="make a reversible local edit inside owned files", alt_need="finish a granted read-write step", outcome="autonomous continuation within scope", constraint="The change is local and already authorized.", negation="do not stop for preference that is not needed", boundary="continuing is within authority.")),
        "ask": (("ask_user",), dict(actor="The assistant", need="choose between two product directions", alt_need="get a missing threshold preference", outcome="a question to the user", constraint="The choice changes the result and is not inferable.", negation="do not invent the preference", boundary="user input is required.")),
        "approval": (("approval_review",), dict(actor="The release step", need="publish or send an external artifact", alt_need="perform an irreversible external action", outcome="approval review before proceeding", constraint="The next action crosses the workspace boundary.", negation="do not treat preparation as permission to publish", boundary="approval is required before action.")),
        "root": (("root_escalation",), dict(actor="The subtask", need="modify a file owned by another active worker", alt_need="coordinate overlapping implementation surfaces", outcome="root escalation for ownership", constraint="Parallel ownership makes an isolated edit unsafe.", negation="do not overwrite peer work", boundary="root coordination resolves the conflict.")),
        "none": ((), dict(actor="The request", need="decide authority from missing facts", alt_need="act on a path not present in the escalation choices", outcome="no acceptable escalation choice", constraint="No offered escalation is safe with the available facts.", negation="no offered escalation should be selected to hide uncertainty", boundary="no listed escalation is safe.")),
    },
}


def _stable_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _pretty_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _opaque(*parts: object) -> str:
    return hashlib.sha256(_stable_json(parts).encode("utf-8")).hexdigest()[:16]


def _examples_jsonl(examples: list[dict]) -> str:
    return "".join(_stable_json(row) + "\n" for row in examples)


def _choice_ids(roles: tuple[str, ...], rng: random.Random) -> dict[str, str]:
    ids = {}
    for role in roles:
        while True:
            cid = f"c{rng.randrange(1 << 48):012x}"
            if cid not in ids.values():
                ids[role] = cid
                break
    return ids


def _eligible_roles(roles: tuple[str, ...], labels: tuple[str, ...],
                    split: str, variant: int) -> tuple[str, ...]:
    if split != "train" or variant != 0:
        return roles
    removable = [role for role in roles if role not in labels]
    if not removable:
        return roles
    removed = removable[variant % len(removable)]
    return tuple(role for role in roles if role != removed)


def _case_limits(per_case: dict[str, int] | None) -> dict[str, int]:
    limits = dict(PER_CASE_BY_SPLIT)
    if per_case is not None:
        if set(per_case) != set(SPLITS):
            raise ValueError("per_case must name train, calibration, and test")
        limits.update(per_case)
    for split, count in limits.items():
        if type(count) is not int or not 1 <= count <= len(STATE_FORMS[split]):
            raise ValueError("per-case counts must fit the available template bank")
    return limits


def _example(family: str, split: str, case_name: str, variant: int,
             fields: dict, labels: tuple[str, ...], rng: random.Random) -> tuple[dict, dict]:
    roles = tuple(ROLE_DESCRIPTIONS[family])
    ids = _choice_ids(roles, rng)
    choices = [{"id": ids[role], "description": ROLE_DESCRIPTIONS[family][role]} for role in roles]
    rng.shuffle(choices)
    eligible_roles = _eligible_roles(roles, labels, split, variant)
    source_group = f"{VERSION}.{family}.{split}.{case_name}"
    source_ref = f"{VERSION}.{family}.{split}.{case_name}.v{variant}"
    opaque = _opaque(source_ref, variant)
    row = {
        "task_family": family,
        "source_group": source_group,
        "request": {
            "schema": "flywheel.decision-request/v1",
            "decision_ref": f"dr:{opaque}",
            "state": STATE_FORMS[split][variant].format(**fields),
            "choices": choices,
            "eligible_choice_ids": [ids[role] for role in eligible_roles],
            "evidence_refs": [f"ev:{opaque}", f"ev:{_opaque(opaque, 'support')}"],
        },
        "acceptable_choice_ids": [ids[role] for role in labels],
        "label_provenance": {"kind": "synthetic", "source_ref": source_ref},
    }
    return row, {
        "source_ref": source_ref, "family": family, "split": split,
        "case": case_name, "variant": variant,
        "label_rule": "synthetic semantic fixture; not measured optimum",
        "acceptable_roles": list(labels),
    }


def generate_corpus(*, seed: int = 1729, per_case: dict[str, int] | None = None) -> dict:
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    limits = _case_limits(per_case)
    rng = random.Random(seed)
    examples: list[dict] = []
    split_by_group: dict[str, str] = {}
    semantic_cases: list[dict] = []
    for family in FAMILIES:
        for split in SPLITS:
            for case_name, (labels, fields) in CASES[family].items():
                for variant in range(limits[split]):
                    row, case_record = _example(family, split, case_name, variant, fields, labels, rng)
                    examples.append(row)
                    split_by_group[row["source_group"]] = split
                    semantic_cases.append(case_record)
    dataset_manifest = build_split_manifest(examples, split_by_group)
    content_digests = {
        "examples_jsonl_sha256": _sha_text(_examples_jsonl(examples)),
        "splits_json_sha256": _sha_text(_pretty_json(split_by_group)),
        "dataset_manifest_sha256": dataset_manifest["manifest_sha256"],
    }
    corpus_manifest = {
        "schema": "flywheel.classifier-synthetic-corpus-manifest/v1",
        "version": VERSION, "seed": seed, "diagnostic_only": True,
        "families": list(FAMILIES), "splits": list(SPLITS),
        "per_case_by_split": limits, "source_group_split_map": split_by_group,
        "content_digests": content_digests, "dataset_manifest": dataset_manifest,
        "semantic_cases": semantic_cases, "does_not_prove": DOES_NOT_PROVE,
    }
    return {"schema": "flywheel.classifier-synthetic-corpus/v1", "version": VERSION,
            "seed": seed, "examples": examples, "splits": split_by_group,
            "manifest": corpus_manifest}


def write_corpus(out_dir: str | Path, *, seed: int = 1729,
                 per_case: dict[str, int] | None = None) -> dict:
    corpus = generate_corpus(seed=seed, per_case=per_case)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "examples.jsonl").write_text(_examples_jsonl(corpus["examples"]), encoding="utf-8", newline="\n")
    (out / "splits.json").write_text(_pretty_json(corpus["splits"]), encoding="utf-8", newline="\n")
    (out / "manifest.json").write_text(_pretty_json(corpus["manifest"]), encoding="utf-8", newline="\n")
    return corpus


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Explicit output directory.")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--train-per-case", type=int, default=PER_CASE_BY_SPLIT["train"])
    parser.add_argument("--calibration-per-case", type=int, default=PER_CASE_BY_SPLIT["calibration"])
    parser.add_argument("--test-per-case", type=int, default=PER_CASE_BY_SPLIT["test"])
    args = parser.parse_args(argv)
    write_corpus(args.out, seed=args.seed, per_case={
        "train": args.train_per_case,
        "calibration": args.calibration_per_case,
        "test": args.test_per_case,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
