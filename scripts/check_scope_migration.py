"""check_scope_migration.py -- the older `does_not_prove` name stays where it belongs.

Records say what they cover in a `scope` field (project-docs/SCOPE-MIGRATION.md).
The older name survives only in the shared readers, in artifacts whose bytes are
sealed or captured, and in historical documents. Any other file that spells it
fails this check, so a new writer cannot bring the old vocabulary back.

    python scripts/check_scope_migration.py           # check; exit 1 on a stray use
    python scripts/check_scope_migration.py --count   # print files and occurrences
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "does_" + "not_prove"   # spelled apart so this file does not match itself

# canon 0.7.0 writes the older field in its released capsule, receipt and report
# format. Each group below is listed file by file; a new canon file that spells the
# name fails the check. The tool migrates as one release (SCOPE-MIGRATION.md).
_CANON_MODULES = (
    # the modules that build, validate, store or report those records
    "bootstrap_runtime.py",
    "bootstrap_runtime_cache.py",
    "canonmd.py",
    "capsule_build.py",
    "capsule_types.py",
    "capsule_validation.py",
    "cli_compile.py",
    "client_capture.py",
    "client_mcp_store.py",
    "context_purge_report.py",
    "context_query.py",
    "context_store.py",
    "doctor.py",
    "import_policy.py",
    "local_mcp.py",
    "omission.py",
    "readiness.py",
    "rescue.py",
    "rescue_artifacts.py",
    "retention_receipts.py",
    "secret_quarantine.py",
    "transform.py",
    "undo_receipts.py",
    "witness.py",
    "workspace/brief.py",
    "workspace/import_write.py",
)
_CANON_KEPT = (
    # the modules above, and the byte-identical copy the client package vendors
    *(f"packages/canon/src/canon/{m}" for m in _CANON_MODULES),
    *(f"packages/canon/client-plugin/server/src/canon/{m}" for m in _CANON_MODULES),
    # tests that assert the field is present in what those modules emit
    "packages/canon/tests/test_client_capture.py",
    "packages/canon/tests/test_client_mcp.py",
    "packages/canon/tests/test_context_purge_closure.py",
    "packages/canon/tests/test_context_related_events.py",
    "packages/canon/tests/test_context_store.py",
    "packages/canon/tests/test_doctor_cli.py",
    "packages/canon/tests/test_import_policy.py",
    "packages/canon/tests/test_import_review.py",
    "packages/canon/tests/test_mcp_check.py",
    # recorded capsules and witnesses the foundation tests load
    "packages/canon/tests/fixtures/foundation/bootstrap_witness_pass.json",
    "packages/canon/tests/fixtures/foundation/capsule_handoff_full.json",
    "packages/canon/tests/fixtures/foundation/capsule_minimal_needle.json",
    "packages/canon/tests/fixtures/foundation/omission_budget_noncritical.json",
    "packages/canon/tests/fixtures/foundation/transform_summary.json",
    # the client-package build and its checks, which read the field from a built package
    "packages/canon/scripts/build_client_package.py",
    "packages/canon/scripts/check_native_client.py",
    "packages/canon/scripts/check_native_workflow.py",
    # the format reference and the dated design records that define the field
    "packages/canon/docs/shared-context.md",
    "packages/canon/project-docs/C1-DECISIONS.md",
    "packages/canon/project-docs/CANON-CONTINUITY-CAPSULE-DESIGN.md",
    "packages/canon/project-docs/MCP-DECISIONS.md",
    "packages/canon/project-docs/W1-WORKSPACE.md",
)

ALLOWED = (
    # the shared readers
    "harness/scope.py",
    "scripts/check_scope_migration.py",
    "harness/receipt_scope.py",   # the v3/v4 receipt vocabulary, kept verbatim
    "desktop/lib/models/scope_field.dart",
    "tests/test_scope_migration.py",
    # vendored, pinned in VENDORED.sha256
    "harness/_vendor/*",
    # pinned by its LF bytes in project-docs/prereg/2026-10-04-shapley-placebo.md
    "harness/shapley_far.py",
    # sealed, anchored, captured, or old-version fixtures
    "artifacts/*",
    "project-docs/lanes/evidence/*",
    "project-docs/records/*",
    "tests/fixtures/*",
    "desktop/test/fixtures/*",
    "docs/art/receipts.json",
    # the same record in each package imported from its own repository
    "packages/*/docs/art/receipts.json",
    # the same record in each demo imported from its own repository
    "demos/*/docs/art/receipts.json",
    # tools imported into packages/ keep the record vocabulary of their own
    # releases until each one migrates; the paths below are theirs
    "packages/learn/scripts/check_client_archive.py",
    "packages/plexus/scripts/build_client_package.py",
    "packages/plexus/scripts/check_native_client.py",
    "packages/plexus/scripts/check_native_workflow.py",
    "packages/mneme/client-plugin/server/src/mneme/origin.py",
    "packages/mneme/scripts/build_client_package.py",
    "packages/mneme/scripts/check_native_client.py",
    "packages/mneme/scripts/check_native_workflow.py",
    "packages/mneme/src/mneme/origin.py",
    "packages/mneme/tests/test_origin_recheck.py",
    "packages/relay/scripts/build_client_package.py",
    "packages/relay/scripts/check_native_client.py",
    "packages/relay/scripts/check_native_workflow.py",
    "packages/index/scripts/build_client_package.py",
    "packages/index/scripts/check_native_client.py",
    "packages/crucible/scripts/build_client_package.py",
    "packages/crucible/scripts/check_native_client.py",
    # forum 1.17.0 writes the field in two records of its released format: the
    # native-client check record, and the route-preflight skill's output (that
    # skill's files are byte-pinned release material in forum's .gitattributes)
    "packages/forum/scripts/check_native_forum.py",
    "packages/forum/src/forum/skills/forum-route-preflight/scripts/forum_route_preflight.py",
    # bulletin 0.5.0 answers /v1/reports with the field; the deployed board
    # serves that response today, and its smoke and its test read it back
    "packages/bulletin/scripts/smoke.mjs",
    "packages/bulletin/src/reports.ts",
    "packages/bulletin/test/reports.test.ts",
    # articulate 0.18.0 reads version 1 receipts, which name a finding's scope
    # with the older field (scope.py LEGACY_KEY, in the package and in the
    # plugin's vendored copy); its changelog, a ruleset baseline, a recorded
    # receipt set and a test carry the name for that reason
    "packages/articulate/CHANGELOG.md",
    "packages/articulate/claude-plugin/src/articulate/corpus_receipt.py",
    "packages/articulate/claude-plugin/src/articulate/scope.py",
    "packages/articulate/scripts/release_ruleset_baseline.json",
    "packages/articulate/src/articulate/corpus_receipt.py",
    "packages/articulate/src/articulate/scope.py",
    "packages/articulate/tests/house1_receipts.json",
    "packages/articulate/tests/test_corpus_receipt.py",
    # emet's Flywheel reporter reads evaluation artifacts under either name, and its
    # changelog, its guide and its test say so
    "packages/emet/CHANGELOG.md",
    "packages/emet/docs/FLYWHEEL-EVALUATION-RECEIPTS.md",
    "packages/emet/emet/reporters/flywheel.py",
    "packages/emet/test_reporter_flywheel.py",
    # canon writes the field in every capsule, receipt and report of its released
    # format: 74 files, each named in _CANON_KEPT above
    *_CANON_KEPT,
    # and in each research artifact imported from its own repository
    "docs/research/*/docs/art/receipts.json",
    # describes the receipt fields of the engine version the demo pins (1.0.0)
    "demos/flywheel-receipt-demo/FLYWHEEL-TOOLS-EXPLAINED.md",
    "docs/features/pysyft-result-receipt.md",   # wire-format reference for v1 receipts
    "harness/ollama-manifest-digest-provenance-v1.json",   # self-hashed v1 record, beside v2
    "packaging/bundled-lanes/relay.json",   # v1 descriptor, hash-pinned in bundled_lane_expectations
    "docs/schemas/environment-incentive-manifest-v1.json",   # the v1 schema, beside v2
    "desktop/assets/rowan/action-cues/*",
    "desktop/lib/assistant/rowan_action_cue_*",
    # the pages that tell a reader what the older name became
    "docs/MIGRATING-2.0*.md",   # the note and its generated schema page
    "docs/VERSIONING.md",
    # historical documents, left as written
    "CHANGELOG.md",
    "RELEASE-NOTES-*.md",
    "project-docs/SCOPE-MIGRATION.md",
    "docs/superpowers/*",
    "project-docs/plans/*",
    "project-docs/specs/*",
    "project-docs/prereg/*",
    "project-docs/research/*",
    "project-docs/releases/*",
    "project-docs/release/*",
    "project-docs/reports/*",
    "project-docs/drafts/*",
    "project-docs/features/20*",      # dated feature notes
    "project-docs/architecture/*-20*",  # dated architecture records
)


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT,
        capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def allowed(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in ALLOWED)


def occurrences(path: str) -> int:
    try:
        data = (ROOT / path).read_bytes()
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return 0
    return data.count(NAME.encode())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", action="store_true",
                        help="print file and occurrence counts, allowed and stray")
    args = parser.parse_args(argv)
    hits = {path: n for path in tracked_files() if (n := occurrences(path))}
    stray = {path: n for path, n in hits.items() if not allowed(path)}
    if args.count:
        kept = {p: n for p, n in hits.items() if p not in stray}
        print(f"all: {len(hits)} files, {sum(hits.values())} occurrences")
        print(f"kept (allowlisted): {len(kept)} files, {sum(kept.values())} occurrences")
        print(f"stray: {len(stray)} files, {sum(stray.values())} occurrences")
        return 0
    if stray:
        print(f"{NAME} appears outside the allowlist in {len(stray)} files:")
        for path, n in sorted(stray.items()):
            print(f"  {path}: {n}")
        print("Write `scope` with a positive entry, or read old records through "
              "harness/scope.py (project-docs/SCOPE-MIGRATION.md).")
        return 1
    print(f"scope migration: {len(hits)} files keep the older name, all allowlisted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
