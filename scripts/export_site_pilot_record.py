"""Derive the published site record for a cross-harness run from the run itself.

The site renders a figure from a JSON document it hashes and republishes. That
document used to be written by hand, which is how the figure came to say four
attempts while the repository's own record said thirty-five. So this builds it
from the two artifacts that already exist: the graded metric report, and the
scorecard the report was pooled from.

Everything path-shaped is dropped on the way out. The run happens on one
machine, the record is read by everyone else, and an absolute path is both
unverifiable to a reader and a disclosure of whoever ran it.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "zentropy-current-cross-harness-pilot-source/v2"
COMMIT_URL = "https://github.com/HarperZ9/flywheel/commit/"
# The run artifacts a reader could be handed and check. Anything holding an
# attempt's own output stays out: it is unreviewed model text.
RUN_ARTIFACTS = ("manifest.json", "matrix.json", "gate.json", "profiles.json",
                 "comparison-input.json")
# A path on the machine that built the record means nothing to its readers and
# carries the account that ran it. The writer refuses rather than publishing one.
# A bare "://" is not a path, so the drive-letter pattern is anchored to a letter
# and a separator rather than matching every URL in the document.
PATH_MARKERS = (re.compile(r"\b[A-Za-z]:[\\/]"),
                re.compile(r"AppData|/home/|/Users/"))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def role_entry(role):
    """One harness role, with every absence carrying the reason it is absent."""
    return {
        "role": role["provider_role"],
        "attempts": role["attempts"],
        "launched": role["launched"],
        "readable": role["scored"],
        "passed": role["oracle_pass"],
        "passRate": role["pass_rate"],
        "latencyMsMedian": role["latency_ms_median"],
        "latencyMsP90": role["latency_ms_p90"],
        "cost": {
            "usdTotal": role["cost_usd_total"],
            "reportedAttempts": role["cost_reported_attempts"],
            "coverage": role["cost_coverage"],
        },
        "outputTokensTotal": role["output_tokens_total"],
        "modelsObserved": list(role.get("models_observed") or []),
        "ungraded": dict(role.get("unreadable_reasons") or {}),
        "envelopeRecovery": role.get("envelope_recovery"),
        "nullReasons": dict(role.get("null_reasons") or {}),
    }


def parity_artifacts(rows):
    """Group the run's prompt and context hashes by task.

    A task whose roles did not all receive the same bytes keeps the hashes it
    actually had, rather than being dropped or silently collapsed to one.
    """
    tasks = {}
    for row in rows:
        task = tasks.setdefault(row["task_id"], {"taskId": row["task_id"], "roles": set(),
                                                 "prompt": set(), "runtimeContext": set()})
        task["roles"].add(row["provider_role"])
        task["prompt"].add(row["raw_prompt_sha256"])
        task["runtimeContext"].add(row["runtime_context_sha256"])
    out = []
    for task in sorted(tasks.values(), key=lambda item: item["taskId"]):
        identical = len(task["prompt"]) == 1 and len(task["runtimeContext"]) == 1
        out.append({
            "taskId": task["taskId"],
            "roles": len(task["roles"]),
            "prompt": {"sha256": sorted(task["prompt"])},
            "runtimeContext": {"sha256": sorted(task["runtimeContext"])},
            "identicalAcrossRoles": identical,
        })
    return out


def receipt_records(rows):
    """Public identity for each attempt's receipt, with no path and no output."""
    records = []
    for row in sorted(rows, key=lambda item: (item["provider_role"], item["task_id"])):
        path = row.get("receipt_path") or ""
        subject = None
        digest = None
        if path and Path(path).is_file():
            digest = sha256_file(path)
            try:
                document = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                document = {}
            subject = document.get("receipt_subject_sha256")
        records.append({
            "role": row["provider_role"],
            "taskId": row["task_id"],
            "state": row.get("receipt_state") or "unknown",
            "receiptSha256": digest,
            "receiptSubjectSha256": subject,
        })
    return records


def build(report, scorecard, run_root):
    rows = scorecard["rows"]
    roles = [role_entry(role) for role in sorted(report["roles"],
                                                 key=lambda item: item["provider_role"])]
    records = receipt_records(rows)
    parity = parity_artifacts(rows)
    every_task_identical = all(task["identicalAcrossRoles"] for task in parity)
    verdict = "byte-identical" if parity and every_task_identical else "mixed"
    hashes = {}
    for name in RUN_ARTIFACTS:
        candidate = Path(run_root) / name
        if candidate.is_file():
            hashes[name] = sha256_file(candidate)
    commit = (report.get("source_commits") or [None])[0]
    return {
        "schema": SCHEMA,
        "capturedAt": "2026-09-04",
        "classification": "graded-cross-harness-run",
        "runId": (report.get("run_ids") or [None])[0],
        "taskSetId": (report.get("task_set_ids") or [None])[0],
        "sourceCommit": commit,
        "sourceCommitUrl": COMMIT_URL + commit if commit else None,
        "evidenceAvailability": "operator-local-hash-only",
        "sourceTreeState": scorecard.get("source_tree_state"),
        "counts": {
            "roles": len(roles),
            "tasks": len(parity),
            "attempts": report["counts"]["attempts"],
            "launched": report["counts"]["launched"],
            "readable": report["counts"]["scored"],
            "passed": sum(role["passed"] for role in roles),
            "gradedCheckers": report["counts"]["graded_checkers"],
        },
        "parity": {"prompt": verdict, "runtimeContext": verdict},
        "parityArtifacts": parity,
        "roles": roles,
        "checkers": report["checkers"],
        "receipts": {
            "attempts": len(records),
            "verified": sum(1 for record in records if record["state"] == "verified"),
            "records": records,
        },
        "observations": {
            # Stated per role above. Repeated here as a null so a reader who
            # scans only this block does not read silence as zero.
            "costUsd": "per role; unmeasured where the provider states none",
            "resourceUse": None,
            "observedModelIdentity": "per role",
        },
        "artifactHashes": hashes,
        "limitations": report["does_not_prove"],
        "doesNotProve": (
            "The run is one repetition per task on one machine. Nothing here is a market "
            "performance claim, a quality ranking, or a statement about a customer workload."
        ),
    }


def render(record):
    """Serialize, refusing to emit a document that carries a local path."""
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    for marker in PATH_MARKERS:
        found = marker.search(text)
        if found:
            raise ValueError(f"refusing to publish a record containing {found.group(0)!r}")
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="graded metric report JSON")
    parser.add_argument("--scorecard", required=True, help="pooled scorecard the report used")
    parser.add_argument("--run-root", required=True, help="directory holding the run artifacts")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    scorecard = json.loads(Path(args.scorecard).read_text(encoding="utf-8"))
    record = build(report, scorecard, args.run_root)
    Path(args.out).write_text(render(record), encoding="utf-8", newline="\n")

    counts = record["counts"]
    receipts = record["receipts"]
    print(f"wrote {args.out}: {counts['roles']} roles, {counts['attempts']} attempts, "
          f"{counts['readable']} readable, {counts['passed']} passed, "
          f"{receipts['verified']}/{receipts['attempts']} receipts verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
