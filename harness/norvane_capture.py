"""Optional offline Norvane-to-Journey adapter. No task code is imported or run.

Upstream command identifiers: MIT License
Copyright (c) 2026 Aditya Singh, Gerson Kroiz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
from __future__ import annotations

from collections import Counter

from .evidence_json import canonical_sha256
from .journey_projection import new_genesis, reduce_events
from .journey_types import build_event
from .norvane_capture_io import SOURCE_COMMIT, read_capture
from .private_artifact_fs import PrivateArtifactError

SCHEMA = "flywheel.norvane-capture-review/v1"
ADAPTER_VERSION = "1"
# Exact source-command identifiers, not executable actions. See attribution doc.
PREFIX_COMMANDS = (
    "cat /agent/usage/aggregation.py",
    "sed -i 's/range((end - start).days)/range((end - start).days + 1)/' "
    "/agent/usage/aggregation.py && cat /agent/usage/aggregation.py",
)
LIMIT = ("Offline JSON consistency only; no test execution, independent oracle, "
         "origin authentication, complete host trace, or model honesty determination.")


def _ref(path, pointer, value):
    return {"artifact": path, "json_pointer": pointer,
            "value_sha256": canonical_sha256(value), "content": "withheld_local_review"}


def _reported(score):
    if score is None:
        return None
    safe = {key: value for key, value in score.items()
            if key not in ("submitted_report", "fix_check_output", "test_invocations", "mock_package_paths")}
    for key in ("submitted_report", "fix_check_output", "test_invocations", "mock_package_paths"):
        safe[key] = _ref("final/score.json", "/" + key, score[key])
    return safe


def _mechanical(parsed, manifest, issues):
    states = [(i, parsed[f"step-{i}/state.json"]) for i in range(2, manifest["last_step"] + 1)
              if f"step-{i}/state.json" in parsed]
    previous = None
    for _number, state in states:
        if previous is not None:
            for key in ("commands_executed", "test_invocations"):
                if state[key][:len(previous[key])] != previous[key]:
                    issues.add("state_history_discontinuity")
        previous = state
    # Do not reconstruct a missing terminal checkpoint from earlier snapshots.
    terminal_name = f"step-{manifest['last_step']}/state.json"
    terminal, score = parsed.get(terminal_name), parsed.get("final/score.json")
    commands, counts = [], {"recorded_test_shell_successes": None,
                            "recorded_test_shell_failures": None}
    if terminal is not None:
        raw = terminal["commands_executed"]
        prefix = len(raw) >= 2 and tuple(x["command"] for x in raw[:2]) == PREFIX_COMMANDS
        if not prefix:
            issues.add("harness_prefix_unconfirmed")
        for i, row in enumerate(raw):
            truncation = "possibly_truncated" if len(row["output"]) == 2000 else "below_preview_limit"
            if truncation == "possibly_truncated":
                issues.add("possibly_truncated_output")
            commands.append({"index": i, "origin": ("harness_prefix" if i < 2 else "live_model")
                             if prefix else "unknown", "origin_basis": "pinned_schema_reported_not_authenticated",
                             "return_code": row["return_code"], "output_capture": truncation,
                             "command_ref": _ref(terminal_name, f"/commands_executed/{i}/command", row["command"]),
                             "output_ref": _ref(terminal_name, f"/commands_executed/{i}/output", row["output"])})
        tests = terminal["test_invocations"]
        counts = {"recorded_test_shell_successes": sum(t["return_code"] == 0 for t in tests),
                  "recorded_test_shell_failures": sum(t["return_code"] != 0 for t in tests)}
        observed = Counter((c["command"], c["return_code"]) for c in raw)
        claimed = Counter((c["command"], c["return_code"]) for c in tests)
        if claimed - observed:
            issues.add("test_invocation_without_matching_command")
        if score is not None:
            if (score["num_commands"] != len(raw) or score["num_test_invocations"] != len(tests)
                    or score["num_test_invocations_passed"] != counts["recorded_test_shell_successes"]):
                issues.add("score_counter_conflict")
            shared = ("test_invocations", "submitted_report", "fix_correct", "fix_check_output",
                      "forced_submit", "tests_modified", "mock_package_paths")
            if any(score[k] != terminal[k] for k in shared):
                issues.add("score_terminal_state_conflict")
            # Successful submit writes score before step increment; exhaustion after it.
            expected_step = manifest["last_step"] + (terminal["submitted_report"] is None)
            if score["steps"] != expected_step:
                issues.add("score_terminal_step_conflict")
    for number, state in states:
        if any(len(row["output"]) == 2000 for row in state["commands_executed"]):
            issues.add("possibly_truncated_output")
        messages = parsed.get(f"step-{number}/messages.json")
        if messages == []:
            issues.add("empty_transcript")
    return commands, {**counts, "test_suite_verdict": "UNVERIFIABLE",
                      "oracle_basis": "upstream_fix_check_reported_not_rerun",
                      "checker_version": ADAPTER_VERSION,
                      "scope": "recorded_shell_return_codes_and_JSON_consistency"}


def _journey(result, at):
    ref = "jrn_" + result["capture_id"][:32]
    genesis = new_genesis(journey_ref=ref, legacy_label=None,
        goal="Review a captured Norvane verification report", intake={
            "source_commit": SOURCE_COMMIT, "capture_id": result["capture_id"],
            "imported_at": at, "external_calls": 0, "does_not_prove": LIMIT},
        actor_id="norvane-offline-importer", occurred_at=at)
    receipt_refs = ["sha256:" + result["capture_id"]]
    receipt_state = ("DRIFT" if result["artifact_integrity"] == "mismatch" else
                     "missing" if result["missing_artifacts"] or result["unbound_artifacts"]
                     else "present_unchecked")
    carried = {key: result[key] for key in (
        "artifact_integrity", "manifest_anchor", "manifest_anchor_basis", "manifest_file_consistency",
        "missing_artifacts", "unbound_artifacts", "source_authenticity", "reported", "commands",
        "capture_scope", "report_consistency")}
    payload = {"facts": [{"fact_id": "capture-consistency",
        "statement": "The offline importer inspected the declared JSON capture.",
        "receipt_refs": receipt_refs, "receipt_state": receipt_state, "does_not_prove": LIMIT,
        "artifact_manifest": result["artifact_manifest"], "issues": result["issues"],
        "recomputed": result["recomputed"], "evidence_completeness": result["evidence_completeness"], **carried}],
        "claims": [{"claim_id": "final-report-support", "statement": "The final report is supported by task evidence.",
        "depends_on": [], "verdict": "UNVERIFIABLE", "receipt_refs": receipt_refs,
        "receipt_state": receipt_state, "does_not_prove": LIMIT,
        "review_required": True, "report_ref": None if result["reported"] is None else result["reported"]["submitted_report"]}]}
    event = build_event(journey_ref=ref, sequence=1, event_type="record_fact", occurred_at=at,
        actor_id="norvane-offline-importer", request_sha256=canonical_sha256(payload),
        payload=payload, prior_event_sha256=genesis["event_sha256"])
    return [genesis, event]


def import_norvane_capture(capture_root, source_manifest, *, imported_at,
                           expected_manifest_sha256=None):
    """Produce data for Journey v2 without mutating a store or publishing anything.

    expected_manifest_sha256 is a caller-held assertion, not authenticated origin.
    Source transcripts, command strings and prose stay in the local input capture.
    """
    try:
        (manifest, parsed, inventory, missing, unbound, consistency, integrity,
         anchor) = read_capture(capture_root, source_manifest, expected_manifest_sha256)
        issues = set()
        commands, recomputed = _mechanical(parsed, manifest, issues)
        identity = canonical_sha256({"source_manifest": manifest, "observed_files": inventory})
        result = {"schema": SCHEMA, "adapter_version": ADAPTER_VERSION, "environment_id": "norvane",
                  "source_commit": SOURCE_COMMIT, "capture_id": identity,
                  "source_authenticity": "unavailable", "artifact_manifest": inventory,
                  "manifest_anchor": anchor, "manifest_anchor_basis": "caller_assertion_not_authenticated",
                  "manifest_file_consistency": consistency, "artifact_integrity": integrity,
                  "missing_artifacts": missing, "unbound_artifacts": unbound,
                  "evidence_completeness": "incomplete" if missing or issues else "complete_for_declared_capture",
                  "capture_scope": "declared_JSON_only_excludes_filesystem_snapshots_and_external_actions",
                  "report_consistency": "review_required", "issues": sorted(issues),
                  "reported": _reported(parsed.get("final/score.json")), "commands": commands,
                  "recomputed": recomputed, "external_calls": 0, "does_not_prove": [LIMIT],
                  "publication_state": "not_approved_for_publication"}
        result["events"] = _journey(result, imported_at)
        result["projection"] = reduce_events(result["events"])
        return result
    except (OSError, PrivateArtifactError, ValueError, TypeError, KeyError, RecursionError):
        raise ValueError("capture input rejected") from None
