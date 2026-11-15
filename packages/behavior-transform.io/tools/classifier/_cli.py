"""CLI entry point for the classifier package."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from pressure_scan import PROFILES, _default_paths, _pressure_label  # type: ignore[import-not-found]
from classifier._policy import (_VALID_ACTIONS, PolicyDef, _active_policy,
    policy_list_cmd, policy_show_cmd, policy_activate_cmd, policy_save_cmd,
    policy_delete_cmd, policy_diff_cmd, policy_export_cmd, policy_import_cmd)
from classifier._audit import audit_log_cmd, _audit_write
from classifier._ci import fence_check, hook_install, hook_remove, probe_cmd, status_cmd
from classifier._analysis import (unified_report, enforce_plan, pipeline_report,
    save_baseline, drift_report, budget_summary, modulate_report, window_report, compound_report)
from classifier._context import analyze_context, annotate_file, validate_file, ctx_fix
from classifier._inference import (bypass_source, intercept_stream, full_bypass,
    rephrase_source, emit_calibration_map, inference_calibrate_cmd, CalibrationPipeline,
    _INFERENCE_STRENGTHS)
from classifier._refusal import RefusalModulator, refusal_manage_cmd
from classifier._prompt import (prompt_modulate_cmd, prompt_session_cmd, family_list_cmd,
    FamilyModulator, _PROMPT_ROLES, _PROMPT_FORMATS, _FAMILY_PROFILES)


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="AUP classifier evasion layer + policy management")
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--json",        action="store_true")
    ap.add_argument("--no-tier2",    action="store_true")
    ap.add_argument("--profile",     choices=list(PROFILES), default=None)
    ap.add_argument("--threshold",   type=float, default=30.0,
                    help="Block threshold for budget/drift/enforce (default 30.0)")
    ap.add_argument("--dry-run",     action="store_true",
                    help="With --ctx-fix / --enforce: report changes without writing")
    ap.add_argument("--audit-limit", type=int, default=50,
                    help="Lines to show with --audit-log (default 50)")
    # Policy save options
    ap.add_argument("--policy-desc",         metavar="TEXT",  default="",
                    help="Description for --policy-save")
    ap.add_argument("--tier1-action",        choices=list(_VALID_ACTIONS), default="block",
                    help="Tier 1 hit action for --policy-save (default: block)")
    ap.add_argument("--tier2-action",        choices=list(_VALID_ACTIONS), default="warn",
                    help="Tier 2 hit action for --policy-save (default: warn)")
    ap.add_argument("--fail-over-threshold", action="store_true",
                    help="Gate/fence fails on files exceeding threshold (for --policy-save)")
    # Modulation options
    ap.add_argument("--window-size",  type=int, default=10, metavar="N",
                    help="Lines per sliding window for --window (default 10)")
    ap.add_argument("--min-co-count", type=int, default=2,  metavar="N",
                    help="Min distinct terms for compound detection (default 2)")
    # Pipeline options
    ap.add_argument("--output",       metavar="FILE",   default=None,
                    help="Output file for --rephrase / --infer-calibrate / "
                         "--refusal-manage (default: stdout)")
    ap.add_argument("--content-type",
                    choices=sorted(CalibrationPipeline.CONTENT_TYPES),
                    default="auto",
                    help="Content type for pipeline routing (default: auto)")
    # Inference calibration + refusal management options
    ap.add_argument("--inference-strength",
                    choices=sorted(_INFERENCE_STRENGTHS), default="moderate",
                    help="Inference calibration strength (default: moderate)")
    ap.add_argument("--no-vocab", action="store_true",
                    help="Skip vocabulary calibration stage (inference layer only)")
    ap.add_argument("--target-prob", type=float, default=0.10, metavar="P",
                    help="Refusal probability target for --refusal-manage / "
                         "--pipeline-run / --prompt-modulate (default: 0.10)")
    # Prompt modulation options
    ap.add_argument("--prompt-role",
                    choices=list(_PROMPT_ROLES), default="user",
                    help="Role context for prompt calibration (default: user)")
    ap.add_argument("--prompt-format",
                    choices=list(_PROMPT_FORMATS), default="text",
                    help="Prompt input format: text | json | messages (default: text)")
    ap.add_argument("--model-family",
                    choices=sorted(_FAMILY_PROFILES), default=None,
                    metavar="{" + ",".join(sorted(_FAMILY_PROFILES)) + "}",
                    help="Target model family for family-aware calibration; "
                         "overrides --target-prob and --inference-strength")
    grp = ap.add_mutually_exclusive_group(required=True)
    # Evasion analysis
    grp.add_argument("--ctx",      action="store_true", help="Session context pressure child safety assessment")
    grp.add_argument("--annotate", metavar="FILE",      help="Per-segment heat-child safety assessment")
    grp.add_argument("--validate", metavar="FILE",      help="Before/after calibration score")
    grp.add_argument("--budget",   action="store_true", help="Aggregate tree budget")
    grp.add_argument("--baseline", action="store_true", help="Save pressure snapshot")
    grp.add_argument("--drift",    action="store_true", help="Regressions vs snapshot")
    grp.add_argument("--pipeline", action="store_true",
                     help="End-to-end: discover + lint + budget + gate")
    grp.add_argument("--gate",     action="store_true",
                     help="CI gate: exits 1 if Tier 1 hits or BLOCK pressure")
    grp.add_argument("--ctx-fix",  action="store_true",
                     help="Apply calibrations to auto-loaded context files in-place")
    grp.add_argument("--fence",    action="store_true",
                     help="Session fence: check context against active policy")
    grp.add_argument("--report",   action="store_true",
                     help="Unified report: policy + context + tree + drift")
    grp.add_argument("--enforce",  action="store_true",
                     help="Remediation plan for active policy (auto-executes safe steps)")
    # Policy management
    grp.add_argument("--policy-list",     action="store_true", help="List all policies")
    grp.add_argument("--policy-show",     metavar="NAME",      help="Show policy details")
    grp.add_argument("--policy-activate", metavar="NAME",      help="Set active policy")
    grp.add_argument("--policy-save",     metavar="NAME",      help="Save a custom policy")
    grp.add_argument("--policy-delete",   metavar="NAME",      help="Delete a custom policy")
    grp.add_argument("--policy-active",   action="store_true", help="Show active policy")
    grp.add_argument("--policy-diff",     nargs=2, metavar="NAME",
                     help="Compare two policies side by side")
    grp.add_argument("--policy-export",   metavar="NAME",
                     help="Export policy as portable JSON blob (stdout or --json)")
    grp.add_argument("--policy-import",   metavar="FILE",
                     help="Import policy from exported JSON file")
    grp.add_argument("--audit-log",       action="store_true",
                     help="Show recent policy evaluation audit log")
    # Complete bypass / intercept / hook lifecycle
    grp.add_argument("--bypass",       metavar="SOURCE",
                     help="Calibrate FILE or '-' (stdin) -> stdout; stats to stderr")
    grp.add_argument("--intercept",    action="store_true",
                     help="Streaming calibration: stdin -> calibrated stdout")
    grp.add_argument("--full-bypass",  action="store_true",
                     help="One-shot: calibrate ctx + tree, verify, report (exits 0 on clean)")
    grp.add_argument("--hook-install", action="store_true",
                     help="Install AUP gate as .git/hooks/pre-commit")
    grp.add_argument("--hook-remove",  action="store_true",
                     help="Remove AUP-managed .git/hooks/pre-commit")
    # Modulation commands
    grp.add_argument("--modulate", action="store_true",
                     help="Context-type modulation: per-region weighted pressure child safety assessment")
    grp.add_argument("--window",   action="store_true",
                     help="Sliding-window density: find local pressure peaks (--window-size N)")
    grp.add_argument("--compound", action="store_true",
                     help="Co-occurrence compound detection (--min-co-count N)")
    # Canonical pipeline surface
    grp.add_argument("--rephrase",         metavar="SOURCE",
                     help="Calibrate FILE or '-' (stdin) through the rephrasing pipeline")
    grp.add_argument("--infer-calibrate",  metavar="SOURCE",
                     help="Apply vocabulary + inference calibration to FILE or '-'")
    grp.add_argument("--refusal-manage",   metavar="SOURCE",
                     help="Estimate refusal probability and modulate to --target-prob")
    grp.add_argument("--pipeline-run",     metavar="SOURCE",
                     help="Full interaction pipeline trace: input->modulate->translate->output")
    grp.add_argument("--prompt-modulate",  metavar="TEXT",
                     help="Calibrate a prompt string for model submission "
                          "(--prompt-role / --prompt-format / --model-family)")
    grp.add_argument("--prompt-session",   action="store_true",
                     help="Interactive prompt calibration session: stdin->calibrated stdout")
    grp.add_argument("--family-list",      action="store_true",
                     help="List all model-family calibration profiles and their settings")
    grp.add_argument("--probe",            action="store_true",
                     help="Self-test all calibration stages; exits 0 if pipeline is ready")
    grp.add_argument("--status",           action="store_true",
                     help="Canonical pipeline health and integration surface")
    grp.add_argument("--emit-calibration", metavar="SOURCE",
                     help="Emit calibration child safety assessment for a source (non-destructive)")
    args = ap.parse_args(argv)

    include_tier2 = (
        PROFILES[args.profile]["include_tier2"] if args.profile else not args.no_tier2
    )
    paths = [Path(p) for p in args.paths] if args.paths else _default_paths()

    # --- Policy management ---

    if args.policy_list:
        data = policy_list_cmd()
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            active_name = next((p["name"] for p in data if p["active"]), "guarded")
            print(f"Policies  (active: {active_name!r})")
            print(f"  {'*':1}  {'Name':20}  {'T1':12}  {'T2':12}  {'Thr':5}  Description")
            print("-" * 90)
            for p in data:
                marker  = "*" if p["active"] else " "
                tag     = " [built-in]" if p["builtin"] else " [custom]"
                print(f"  {marker}  {p['name']:20}  {p['tier1_action']:12}  "
                      f"{p['tier2_action']:12}  {p['threshold']:>5.0f}  "
                      f"{p['description'][:32]}{tag}")
        return 0

    if args.policy_show:
        data = policy_show_cmd(args.policy_show)
        if data is None:
            sys.stderr.write(f"Unknown policy: {args.policy_show!r}\n")
            return 2
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            active_tag  = "  [ACTIVE]"   if data.get("active")  else ""
            builtin_tag = "  [built-in]" if data.get("builtin") else "  [custom]"
            print(f"Policy: {data['name']!r}{active_tag}{builtin_tag}")
            print(f"  Description:          {data['description']}")
            print(f"  Tier 1 action:        {data['tier1_action']}")
            print(f"  Tier 2 action:        {data['tier2_action']}")
            print(f"  Threshold:            {data['threshold']:.1f}")
            print(f"  Fail over threshold:  {data['fail_on_over_threshold']}")
            if data.get("created_at"):
                print(f"  Created:              {data['created_at']}")
            if data.get("updated_at"):
                print(f"  Updated:              {data['updated_at']}")
        return 0

    if args.policy_activate:
        result = policy_activate_cmd(args.policy_activate)
        if "error" in result:
            sys.stderr.write(result["error"] + "\n")
            return 2
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Active policy set to: {result['activated']!r}  "
                  f"(was: {result['previous']!r})")
        return 0

    if args.policy_save:
        result = policy_save_cmd(
            args.policy_save, args.policy_desc,
            args.tier1_action, args.tier2_action,
            args.threshold, args.fail_over_threshold,
        )
        if "error" in result:
            sys.stderr.write(result["error"] + "\n")
            return 2
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            p = result["policy"]
            print(f"Policy saved: {result['saved']!r}  "
                  f"T1={p['tier1_action']}  T2={p['tier2_action']}  "
                  f"threshold={p['threshold']:.0f}")
        return 0

    if args.policy_delete:
        result = policy_delete_cmd(args.policy_delete)
        if "error" in result:
            sys.stderr.write(result["error"] + "\n")
            return 2
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Policy deleted: {result['deleted']!r}")
        return 0

    if args.policy_active:
        policy = _active_policy()
        if args.json:
            print(json.dumps(asdict(policy), indent=2))
        else:
            print(f"Active policy: {policy.name!r}")
            print(f"  {policy.description}")
            print(f"  T1={policy.tier1_action}  T2={policy.tier2_action}  "
                  f"threshold={policy.threshold:.0f}  "
                  f"fail_over_threshold={policy.fail_on_over_threshold}")
        return 0

    if args.policy_diff:
        name_a, name_b = args.policy_diff
        result = policy_diff_cmd(name_a, name_b)
        if "error" in result:
            sys.stderr.write(result["error"] + "\n")
            return 2
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["identical"]:
                print(f"Policies {name_a!r} and {name_b!r} are identical.")
            else:
                print(f"Diff: {name_a!r} vs {name_b!r}  ({len(result['diffs'])} field(s) differ)")
                print(f"  {'Field':30}  {'a':20}  {'b':20}")
                print("-" * 75)
                for field_name, vals in result["diffs"].items():
                    print(f"  {field_name:30}  {str(vals['a']):20}  {str(vals['b']):20}")
        return 0

    if args.policy_export:
        result = policy_export_cmd(args.policy_export)
        if "error" in result:
            sys.stderr.write(result["error"] + "\n")
            return 2
        print(json.dumps(result, indent=2))
        return 0

    if args.policy_import:
        try:
            raw = json.loads(Path(args.policy_import).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            sys.stderr.write(f"Cannot read import file: {e}\n")
            return 2
        result = policy_import_cmd(raw)
        if "error" in result:
            sys.stderr.write(result["error"] + "\n")
            return 2
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Policy imported: {result['saved']!r}")
        return 0

    if args.audit_log:
        entries = audit_log_cmd(limit=args.audit_limit)
        if args.json:
            print(json.dumps(entries, indent=2))
        else:
            if not entries:
                print("Audit log empty.")
            else:
                print(f"Audit log  ({len(entries)} entries, newest last)")
                print(f"  {'Timestamp':20}  {'Event':25}  Details")
                print("-" * 90)
                for e in entries:
                    ts    = e.get("ts", "?")
                    ev    = e.get("event", "?")
                    extra = {k: v for k, v in e.items() if k not in ("ts", "event")}
                    detail = "  ".join(f"{k}={v!r}" for k, v in list(extra.items())[:4])
                    print(f"  {ts:20}  {ev:25}  {detail}")
        return 0

    # --- Fence ---

    if args.fence:
        if args.profile:
            preset = PROFILES[args.profile]
            pol: PolicyDef | None = PolicyDef(
                name=args.profile,
                description=f"Profile override: {args.profile}",
                tier1_action="block",
                tier2_action="block" if preset.get("fail_tier2") else "warn",
                threshold=args.threshold,
                fail_on_over_threshold=bool(preset.get("fail_tier2", False)),
                builtin=True,
            )
        else:
            pol = _active_policy()
        r = fence_check(include_tier2, pol)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            lbl = "PASS" if r["fence_pass"] else "FAIL"
            print(f"Fence [{lbl}]  policy={r['policy']!r}  "
                  f"pressure={r['max_pressure']:.1f}  "
                  f"T1={r['total_t1']} ({r['tier1_action']})  "
                  f"T2={r['total_t2']} ({r['tier2_action']})")
            if r["blocked_by_t1"]:
                print(f"  Blocked: {r['total_t1']} Tier 1 hit(s) — action=block")
                print("  Remedy:  classifier.py --ctx-fix")
            if r["blocked_by_threshold"]:
                print(f"  Blocked: max pressure {r['max_pressure']:.1f} "
                      f">= threshold {r['threshold']:.0f}")
            if r["fence_pass"]:
                print(f"  Context files checked: {r['context_files']}")
        return 0 if r["fence_pass"] else 1

    # --- Unified report ---

    if args.report:
        pol = _active_policy()
        r = unified_report(paths, include_tier2, args.threshold, pol)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            over_lbl  = "PASS" if r["overall_pass"]          else "FAIL"
            fence_lbl = "PASS" if r["fence"]["fence_pass"]   else "FAIL"
            gate_lbl  = "PASS" if r["pipeline"]["gate_pass"] else "FAIL"
            print(f"AUP Report [{over_lbl}]  policy={r['policy']['name']!r}")
            print()
            print(f"  Fence [{fence_lbl}]  "
                  f"context_pressure={r['fence']['max_pressure']:.1f}  "
                  f"T1={r['fence']['total_t1']}  T2={r['fence']['total_t2']}")
            print(f"  Gate  [{gate_lbl}]  "
                  f"tree_score={r['pipeline']['total_score']:.1f}  "
                  f"T1_hits={r['pipeline']['tier1_hits']}  "
                  f"files={r['pipeline']['files_with_hits']}/{r['pipeline']['files_scanned']}")
            if r["drift"]:
                d = r["drift"]
                if "error" in d:
                    print("  Drift  [no baseline]")
                else:
                    drift_lbl = "PASS" if d["total_regressions"] == 0 else "WARN"
                    print(f"  Drift [{drift_lbl}]  regressions={d['total_regressions']}  "
                          f"max_delta={d['max_delta']:.1f}")
            else:
                print("  Drift  [no baseline — run --baseline to enable]")
            if r["pipeline"]["uncalibrated_count"]:
                print(f"  Uncalibrated: {r['pipeline']['uncalibrated_count']} term(s)"
                      f" — run term_discover.py for details")
            print()
            if not r["fence"]["fence_pass"]:
                print("  Action required: classifier.py --ctx-fix")
            if not r["pipeline"]["gate_pass"]:
                print("  Action required: pressure_scan.py --fix [paths]")
        return 0 if r["overall_pass"] else 1

    # --- Enforce ---

    if args.enforce:
        r = enforce_plan(paths, include_tier2, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            status = "COMPLIANT" if r["compliant"] else "NON-COMPLIANT"
            mode   = "  [dry-run]" if r["dry_run"] else ""
            print(f"Enforce [{status}]  policy={r['policy']!r}{mode}")
            print(f"  Fence: {'PASS' if r['fence_pass'] else 'FAIL'}  "
                  f"Gate: {'PASS' if r['gate_pass'] else 'FAIL'}  "
                  f"Remediation items: {r['remediation_count']}")
            if r["remediation"]:
                print()
                for step in r["remediation"]:
                    auto = " [auto-executed]" if step["action"] in r["executed"] else ""
                    print(f"  [{step['priority'].upper():8}] {step['target']}")
                    print(f"             Reason: {step['reason']}")
                    print(f"             Action: {step['action']}{auto}")
            elif r["compliant"]:
                print("  No remediation required.")
        return 0 if r["compliant"] else 1

    # --- Existing evasion analysis commands ---

    if args.ctx:
        data = analyze_context(include_tier2)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            total = sum(r["pressure_score"] for r in data)
            print(f"Session context pressure  (aggregate ≈ {total:.1f})")
            print(f"{'Score':>6}  {'T1':>4}  {'T2':>4}  {'Label':>7}  Source")
            print("-" * 80)
            for r in data:
                print(f"  {r['pressure_score']:>5.1f}  {r['tier1']:>4}  {r['tier2']:>4}"
                      f"  {r['pressure_label']:>7}  {r['label']}")
        return 1 if any(r["tier1"] > 0 for r in data) else 0

    if args.annotate:
        data = annotate_file(Path(args.annotate), include_tier2)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            if not data:
                print(f"No hits: {args.annotate}")
            else:
                print(f"Segment heat-child safety assessment: {args.annotate}")
                print(f"{'Score':>6}  {'T1':>4}  {'T2':>4}  {'Lines':>12}  Preview")
                print("-" * 80)
                for r in data:
                    ln = f"L{r['start_line']}-{r['end_line']}"
                    print(f"  {r['pressure_score']:>5.1f}  {r['tier1']:>4}  {r['tier2']:>4}"
                          f"  {ln:>12}  {r['preview']!r:.50s}")
                    if r.get("terms"):
                        unique = {t["original"]: t["calibrated"] for t in r["terms"]}
                        top_items = list(unique.items())[:4]
                        terms_str = ", ".join(f"{o!r}" for o, _ in top_items)
                        if len(unique) > 4:
                            terms_str += f" +{len(unique) - 4}"
                        print(f"             terms: {terms_str}")
        return 0

    if args.validate:
        r = validate_file(Path(args.validate), include_tier2)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            sign = "+" if r["delta"] >= 0 else ""
            print(f"Validate: {args.validate}")
            print(f"  Before  {r['before_score']:.1f} [{r['before_label']}]"
                  f"  ({r['hits_before']} hits)")
            print(f"  After   {r['after_score']:.1f} [{r['after_label']}]"
                  f"  ({r['hits_after']} hits)")
            print(f"  Delta   {sign}{r['delta']:.1f}  ({r['hits_removed']} hits removed)")
            if r.get("substitutions"):
                for term, detail in list(r["substitutions"].items())[:8]:
                    print(f"    {term!r} -> {detail['calibrated']!r}  (x{detail['count']})")
        return 0

    if args.baseline:
        r = save_baseline(paths, include_tier2)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            print(f"Baseline saved: {r['files']} files -> {r['baseline_saved']}")
        return 0

    if args.drift:
        r = drift_report(paths, include_tier2)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            if "error" in r:
                print(r["error"])
                return 2
            print(f"Drift: {r['total_regressions']} regression(s)  "
                  f"max_delta={r['max_delta']:.1f}")
            for reg in r["regressions"][:10]:
                print(f"  +{reg['delta']:.1f}  {reg['before']:.1f}->{reg['after']:.1f}"
                      f"  {reg['path']}")
            if r["new_files_with_hits"]:
                print(f"New files with hits ({len(r['new_files_with_hits'])}):")
                for p in r["new_files_with_hits"][:5]:
                    print(f"  {p}")
        return 1 if r.get("total_regressions", 0) > 0 else 0

    if args.pipeline:
        r = pipeline_report(paths, include_tier2, args.threshold)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            gate_lbl = "PASS" if r["gate_pass"] else "FAIL"
            print(f"Pipeline [{gate_lbl}]  pressure={r['total_score']:.1f}/100"
                  f"  [{r['total_label']}]  T1={r['tier1_hits']}  T2={r['tier2_hits']}"
                  f"  files={r['files_with_hits']}/{r['files_scanned']}")
            if r["uncalibrated_count"]:
                print(f"Uncalibrated terms: {r['uncalibrated_count']}")
                for u in r["uncalibrated_terms"][:5]:
                    print(f"  {u['term']!r}  ({u['category']}, {u['count']}x)")
            if r["files_over_threshold"]:
                print(f"Over threshold ({args.threshold:.0f}):")
                for fo in r["files_over_threshold"][:10]:
                    print(f"  {fo['score']:>5.1f}  [{fo['label']}]  {fo['path']}")
            elif r["top_offenders"]:
                print("Top offenders:")
                for fo in r["top_offenders"][:5]:
                    print(f"  {fo['score']:>5.1f}  [{fo['label']}]  {fo['path']}")
        return 0 if r["gate_pass"] else 1

    if args.gate:
        r = pipeline_report(paths, include_tier2=False, threshold=args.threshold)
        if args.json:
            print(json.dumps({
                "gate_pass": r["gate_pass"],
                "has_tier1": r["has_tier1"],
                "total_score": r["total_score"],
                "threshold": args.threshold,
                "files_over_threshold": len(r["files_over_threshold"]),
            }, indent=2))
        else:
            gate_lbl = "PASS" if r["gate_pass"] else "FAIL"
            print(f"Gate [{gate_lbl}]  pressure={r['total_score']:.1f}"
                  f"  tier1={'yes' if r['has_tier1'] else 'no'}"
                  f"  over_threshold={len(r['files_over_threshold'])}"
                  f"  threshold={args.threshold:.0f}")
        return 0 if r["gate_pass"] else 1

    if args.ctx_fix:
        results = ctx_fix(include_tier2, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            changed = [r for r in results if r["changed"]]
            verb = "Would change" if args.dry_run else "Changed"
            print(f"ctx-fix ({'dry-run' if args.dry_run else 'live'}): "
                  f"{verb} {len(changed)}/{len(results)} context file(s)")
            for r in results:
                status = "changed" if r["changed"] else "clean  "
                print(f"  [{status}]  {r['label']}")
                if r["total"]:
                    print(f"             substitutions={r['substitutions']}")
        return 0

    if args.bypass:
        result = bypass_source(args.bypass, include_tier2)
        if "error" in result:
            sys.stderr.write(f"bypass error: {result['error']}\n")
            return 2
        stats_line = (
            f"bypass: {result['origin']}  "
            f"before={result['before_score']:.1f}[{_pressure_label(result['before_score'])}]  "
            f"after={result['after_score']:.1f}[{_pressure_label(result['after_score'])}]  "
            f"removed={result['hits_removed']}  subs={result['substitutions']}"
        )
        if args.json:
            sys.stderr.write(json.dumps({k: v for k, v in result.items() if k != "calibrated"},
                                        indent=2) + "\n")
        else:
            sys.stderr.write(stats_line + "\n")
        return 0 if result["clean"] else 1

    if args.intercept:
        total = intercept_stream(include_tier2)
        sys.stderr.write(f"intercept: {total} substitution(s)\n")
        return 0

    if args.full_bypass:
        pol = _active_policy()
        r = full_bypass(paths, include_tier2, dry_run=args.dry_run, policy=pol)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            status = "PASS" if r["overall_pass"] else "FAIL"
            mode   = "  [dry-run]" if r["dry_run"] else ""
            print(f"Full-bypass [{status}]  policy={r['policy']!r}{mode}")
            print(f"  Context: {len(r['ctx_files_fixed'])} file(s) fixed  "
                  f"({r['ctx_substitutions']} substitution(s))")
            print(f"  Tree:    {len(r['tree_files_fixed'])} file(s) fixed  "
                  f"({sum(r['tree_substitutions'].values())} substitution(s))")
            print(f"  Verify:  ctx_clean={r['post_ctx_clean']}  "
                  f"gate_pass={r['post_gate_pass']}  "
                  f"residual_score={r['residual_score']:.1f}  "
                  f"residual_T1={r['residual_t1']}")
            if not r["overall_pass"]:
                print("  Residual hits remain — add LINTER_WHITELIST entries for intentional "
                      "archive sites, or run pressure_scan.py --fix for file-level detail.")
        return 0 if r["overall_pass"] else 1

    if args.hook_install:
        hook_path = Path.cwd() / ".git" / "hooks" / "pre-commit"
        result = hook_install(hook_path)
        if "error" in result:
            sys.stderr.write(result["error"] + "\n")
            return 2
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Hook [{result['status']}]  path={result['path']}")
        return 0

    if args.hook_remove:
        hook_path = Path.cwd() / ".git" / "hooks" / "pre-commit"
        result = hook_remove(hook_path)
        if "error" in result:
            sys.stderr.write(result["error"] + "\n")
            return 2
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Hook [{result['status']}]  path={result['path']}")
        return 0

    if args.modulate:
        r = modulate_report(paths, include_tier2)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            total = r["total_adjusted_pressure"]
            print(f"Modulate  files={r['files_analyzed']}  "
                  f"adjusted_pressure={total:.1f}")
            print(f"  Region weights: " +
                  "  ".join(f"{k}={v}" for k, v in r["region_weights"].items()))
            print(f"  By type:")
            for rtype, score in sorted(r["by_region_type"].items(),
                                       key=lambda x: x[1], reverse=True):
                if score > 0:
                    print(f"    {rtype:12}  {score:.1f}")
            if r["hot_regions"]:
                print(f"  Top adjusted regions:")
                for hr in r["hot_regions"][:10]:
                    ln = f"L{hr['start_line']}-{hr['end_line']}"
                    print(f"    adj={hr['adjusted_score']:>6.1f}  "
                          f"[{hr['region_type']:9}]  {ln:>12}  "
                          f"T1={hr['tier1']}  {hr['preview']!r:.40s}")
        return 1 if any(hr["tier1"] > 0 for hr in r["hot_regions"]) else 0

    if args.window:
        r = window_report(paths, include_tier2, window_size=args.window_size)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            lbl = "PASS" if r["max_peak_score"] == 0 else _pressure_label(r["max_peak_score"])
            print(f"Window [{lbl}]  window={r['window_size']}  "
                  f"files_with_peaks={r['files_with_peaks']}  "
                  f"max_peak={r['max_peak_score']:.1f}")
            for p in r["peaks"][:10]:
                ln = f"L{p['peak_start_line']}-{p['peak_end_line']}"
                terms = ", ".join(f"'{t}'" for t in p["terms"][:4])
                if len(p["terms"]) > 4:
                    terms += f" +{len(p['terms']) - 4}"
                print(f"  {p['peak_score']:>6.1f}  [{p['peak_label']:7}]  "
                      f"{ln:>12}  T1={p['tier1']}  {p['path']}")
                if terms:
                    print(f"             terms: {terms}")
        return 1 if r["max_peak_score"] >= 30 else 0

    if args.compound:
        r = compound_report(paths, include_tier2, min_co_count=args.min_co_count)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            lbl = "PASS" if r["compound_regions"] == 0 else "WARN"
            print(f"Compound [{lbl}]  regions={r['compound_regions']}  "
                  f"min_co={r['min_co_count']}  "
                  f"max_score={r['max_compound_score']:.1f}")
            for h in r["hits"][:10]:
                ln = f"L{h['start_line']}-{h['end_line']}"
                terms = ", ".join(f"'{t}'" for t in h["unique_terms"][:4])
                if h["term_count"] > 4:
                    terms += f" +{h['term_count'] - 4}"
                print(f"  compound={h['compound_score']:>6.1f}  "
                      f"base={h['base_score']:.1f}+{h['amplification']:.1f}  "
                      f"{ln:>12}  {h['path']}")
                print(f"             terms({h['term_count']}): {terms}")
        return 1 if r["compound_regions"] > 0 else 0

    # --infer-calibrate
    if getattr(args, "infer_calibrate", None):
        result = inference_calibrate_cmd(
            args.infer_calibrate,
            output=args.output,
            strength=args.inference_strength,
            include_vocab=not args.no_vocab,
            include_tier2=include_tier2,
            dry_run=args.dry_run,
        )
        if "error" in result:
            sys.stderr.write(f"infer-calibrate error: {result['error']}\n")
            return 2
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            ist = result["inference_stats"]
            out_note = f"  -> {result['output_path']}" if result.get("output_path") else \
                       ("  [dry-run]" if result.get("dry_run") else "  -> stdout")
            sys.stderr.write(
                f"infer-calibrate: {result['origin']}  "
                f"strength={result['strength']}  "
                f"vocab_subs={sum(v for v in result['vocab_substitutions'].values() if isinstance(v,int))}  "
                f"infer_transforms={ist.get('transforms_applied',0)}  "
                f"by_category={ist.get('by_category',{})}{out_note}\n"
            )
        return 0

    # --refusal-manage
    if getattr(args, "refusal_manage", None):
        result = refusal_manage_cmd(
            args.refusal_manage,
            output=args.output,
            target_prob=args.target_prob,
            include_tier2=include_tier2,
            dry_run=args.dry_run,
        )
        if "error" in result:
            sys.stderr.write(f"refusal-manage error: {result['error']}\n")
            return 2
        if args.json:
            print(json.dumps({k: v for k, v in result.items() if k != "calibrated"}, indent=2))
        else:
            met_lbl = "MET" if result["target_met"] else "UNMET"
            sys.stderr.write(
                f"refusal-manage [{met_lbl}]: {result['origin']}\n"
                f"  initial:  p={result['initial']['probability']:.3f}"
                f"  [{result['initial']['label']}]\n"
                f"  final:    p={result['final']['probability']:.3f}"
                f"  [{result['final']['label']}]\n"
                f"  target:   p<={result['target_prob']:.2f}  "
                f"stage_reached={result['stage_reached']}\n"
            )
            for tr in result.get("stages_trace", []):
                sys.stderr.write(
                    f"  stage {tr['stage']}:  "
                    f"vocab_subs={tr['vocab_subs']}  "
                    f"infer_transforms={tr['infer_transforms']}  "
                    f"({tr['infer_strength']})  "
                    f"p={tr['probability']:.3f}[{tr['label']}]\n"
                )
        return 0 if result["target_met"] else 1

    # --pipeline-run: full interaction pipeline trace (input->modulate->translate->output)
    if getattr(args, "pipeline_run", None):
        source = args.pipeline_run
        if source == "-":
            text   = sys.stdin.read()
            origin = "<stdin>"
        else:
            try:
                text   = Path(source).read_text(encoding="utf-8", errors="replace")
                origin = source
            except OSError as e:
                sys.stderr.write(f"pipeline-run: cannot read {source}: {e}\n")
                return 2

        modulator = RefusalModulator(target_prob=args.target_prob)

        # Stage 0 — estimate initial refusal probability
        initial_est = modulator.estimate(text, include_tier2=include_tier2)

        # Stages 1-N — modulate to target
        result = modulator.modulate(text, dry_run=args.dry_run)
        result["origin"] = origin

        calibrated = result["calibrated"]
        if not args.dry_run:
            if args.output:
                try:
                    Path(args.output).write_text(calibrated, encoding="utf-8")
                    result["output_path"] = args.output
                except OSError as e:
                    sys.stderr.write(f"pipeline-run: write error: {e}\n")
                    return 2
            else:
                sys.stdout.write(calibrated)

        if args.json:
            print(json.dumps({k: v for k, v in result.items() if k != "calibrated"}, indent=2))
        else:
            met_lbl = "READY" if result["target_met"] else "RESIDUAL-RISK"
            sys.stderr.write(
                f"\nPipeline-run [{met_lbl}]  {origin}\n"
                f"  +- Input          p={initial_est['probability']:.3f}"
                f"  [{initial_est['label']}]"
                f"  T1={initial_est['tier1_hits']}  framing={initial_est['framing_signals']}\n"
            )
            for tr in result.get("stages_trace", []):
                sys.stderr.write(
                    f"  +- Stage {tr['stage']} ({tr['infer_strength']:8})  "
                    f"vocab={tr['vocab_subs']}  infer={tr['infer_transforms']}  "
                    f"-> p={tr['probability']:.3f}[{tr['label']}]\n"
                )
            sys.stderr.write(
                f"  +- Output         p={result['final']['probability']:.3f}"
                f"  [{result['final']['label']}]"
                f"  target=p<={result['target_prob']:.2f}"
                f"  stage={result['stage_reached']}\n\n"
            )
        _audit_write("pipeline.run", {
            "origin":       origin,
            "initial_prob": initial_est["probability"],
            "final_prob":   result["final"]["probability"],
            "target_prob":  args.target_prob,
            "target_met":   result["target_met"],
            "dry_run":      args.dry_run,
        })
        return 0 if result["target_met"] else 1

    # --prompt-modulate  (uses FamilyModulator when --model-family is set)
    if getattr(args, "prompt_modulate", None):
        family = getattr(args, "model_family", None)
        if family:
            fm = FamilyModulator(
                family=family,
                role=args.prompt_role,
                fmt=args.prompt_format,
            )
            result = fm.modulate(args.prompt_modulate, dry_run=args.dry_run)
            if not args.dry_run:
                calibrated = result["calibrated"]
                if args.output:
                    try:
                        Path(args.output).write_text(calibrated, encoding="utf-8")
                        result["output_path"] = args.output
                    except OSError as e:
                        sys.stderr.write(f"prompt-modulate write error: {e}\n")
                        return 2
                else:
                    sys.stdout.write(calibrated)
                    if not calibrated.endswith("\n"):
                        sys.stdout.write("\n")
                    sys.stdout.flush()
            _audit_write("prompt.modulate.family", {
                "family":     family,
                "role":       args.prompt_role,
                "target_met": result["target_met"],
                "dry_run":    args.dry_run,
            })
        else:
            result = prompt_modulate_cmd(
                args.prompt_modulate,
                role=args.prompt_role,
                fmt=args.prompt_format,
                output=args.output,
                dry_run=args.dry_run,
            )
        if "error" in result:
            sys.stderr.write(f"prompt-modulate error: {result['error']}\n")
            return 2
        if args.json:
            sys.stderr.write(json.dumps(
                {k: v for k, v in result.items() if k != "calibrated"}, indent=2) + "\n")
        else:
            met_lbl = "READY" if result["target_met"] else "RESIDUAL"
            family_tag = f"  family={result['family']!r}" if "family" in result else ""
            tgt = result.get("family_target_prob", result.get("target_prob", 0))
            sys.stderr.write(
                f"prompt [{met_lbl}]"
                f"  role={result.get('role', args.prompt_role)!r}"
                f"  fmt={result.get('format', args.prompt_format)!r}"
                f"{family_tag}"
                f"  target_prob={tgt:.2f}\n"
            )
            for tr in result.get("trace", []):
                sys.stderr.write(
                    f"  {tr['initial_label']}({tr['initial_prob']:.3f})"
                    f" -> {tr['final_label']}({tr['final_prob']:.3f})"
                    f"  stage={tr['stage_reached']}"
                    f"  {'OK' if tr['target_met'] else 'RESIDUAL'}\n"
                )
        return 0 if result["target_met"] else 1

    # --prompt-session
    if getattr(args, "prompt_session", False):
        return prompt_session_cmd(role=args.prompt_role, fmt=args.prompt_format)

    # --family-list
    if getattr(args, "family_list", False):
        profiles = family_list_cmd()
        if args.json:
            print(json.dumps(profiles, indent=2))
        else:
            print(f"Model-family calibration profiles  ({len(profiles)} families)")
            print(f"  {'Family':10}  {'Target':8}  {'Strength':10}  {'Threshold':10}  Description")
            print("-" * 100)
            for fp in profiles:
                cats = ",".join(fp["active_categories"][:3])
                if len(fp["active_categories"]) > 3:
                    cats += f"+{len(fp['active_categories'])-3}"
                print(f"  {fp['name']:10}  p<={fp['target_prob']:.2f}    "
                      f"{fp['inference_strength']:10}  "
                      f"<={fp['pressure_threshold']:.0f}        "
                      f"{fp['description'][:55]}")
                print(f"  {'':10}  categories: {cats}")
        return 0

    # --rephrase
    if args.rephrase:
        content_type = getattr(args, "content_type", "auto")
        result = rephrase_source(
            args.rephrase,
            output=getattr(args, "output", None),
            include_tier2=include_tier2,
            content_type=content_type,
            dry_run=args.dry_run,
        )
        if "error" in result:
            sys.stderr.write(f"rephrase error: {result['error']}\n")
            return 2
        if args.json:
            sys.stderr.write(json.dumps(
                {k: v for k, v in result.items()}, indent=2) + "\n")
        else:
            sign = "+" if result.get("delta", 0) >= 0 else ""
            out_note = (
                f"  -> {result['output_path']}" if "output_path" in result
                else ("  [dry-run]" if result.get("dry_run") else "  -> stdout")
            )
            sys.stderr.write(
                f"rephrase: {result['origin']}  "
                f"type={result['content_type']}  "
                f"before={result['before_score']:.1f}[{result['before_label']}]  "
                f"after={result['after_score']:.1f}[{result['after_label']}]  "
                f"delta={sign}{result['delta']:.1f}  "
                f"subs={result['substitutions']}{out_note}\n"
            )
        return 0 if result.get("clean", False) else 1

    # --probe
    if getattr(args, "probe", False):
        r = probe_cmd()
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            status_lbl = "READY" if r["ready"] else "NOT READY"
            print(f"Probe [{status_lbl}]  "
                  f"{r['stages_passed']}/{r['stages_total']} stages passed")
            for s in r["stages"]:
                icon = "+" if s["pass"] else "!"
                detail = s.get("detail") or s.get("error", "")
                print(f"  [{icon}] {s['stage']:35}  {str(detail)[:60]}")
        return 0 if r["ready"] else 1

    # --status
    if args.status:
        r = status_cmd()
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            print(f"AUP Canonical Rephrasing Pipeline  v{r['version']}")
            print(f"  Active policy:    {r['active_policy']!r}")
            print(f"  Policies:         {r['policies_available']}")
            print(f"  Calibration child safety assessment:  {r['calibration_entries']} entries"
                  f"  ({r['keep_terms']} kept)")
            print(f"  Inference patterns: {r['inference_patterns']}"
                  f"  strengths={r['inference_strengths']}"
                  f"  categories={r.get('inference_categories', [])}")
            print(f"  Family profiles:  {r.get('family_profiles', 0)}"
                  f"  families={r.get('family_names', [])}")
            print(f"  Baseline:         {'yes' if r['baseline_exists'] else 'no'}")
            print(f"  Audit log:        {r['audit_log_entries']} entries")
            print(f"  Pre-commit hook:  "
                  f"{'installed' if r['pre_commit_hook'] else 'not installed'}")
            print(f"  Python API:       {r['python_api']}")
            print(f"  Integration:")
            for point in r["integration_surface"]:
                print(f"    {point}")
            print(f"  Paths:")
            for name, path in r["paths"].items():
                print(f"    {name}: {path}")
        return 0

    # --emit-calibration
    if getattr(args, "emit_calibration", None):
        r = emit_calibration_map(args.emit_calibration, include_tier2)
        if "error" in r:
            sys.stderr.write(f"emit-calibration error: {r['error']}\n")
            return 2
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            print(f"Calibration child safety assessment: {r['origin']}  "
                  f"score={r['score']:.1f}[{r['label']}]  "
                  f"T1={r['tier1_hits']}  T2={r['tier2_hits']}")
            if not r["calibration_map"]:
                print("  (no hits — content is already clean)")
            else:
                print(f"  {'Term':35}  {'Calibrated':35}  {'Tier':6}  {'Count':5}")
                print("  " + "-" * 88)
                for entry in r["calibration_map"]:
                    lines_str = str(entry["lines"][:6])[1:-1]
                    if len(entry["lines"]) > 6:
                        lines_str += f" +{len(entry['lines']) - 6}"
                    print(f"  {entry['original']:35}  {entry['calibrated']:35}  "
                          f"{entry['severity']:6}  {entry['count']:5}")
        return 0 if r["tier1_hits"] == 0 else 1

    # --budget
    r = budget_summary(paths, include_tier2, args.threshold)
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"Budget: {r['total_score']:.1f}/100  [{r['total_label']}]  "
              f"threshold={r['threshold']:.0f}  remaining={r['budget_remaining']:.1f}")
        targets = r["files_over_threshold"] or r["top_offenders"][:5]
        label = "Over threshold" if r["files_over_threshold"] else "Top offenders"
        if targets:
            print(f"\n{label}:")
            for o in targets:
                print(f"  {o['score']:>5.1f}  [{o['label']}]  {o['path']}")
    return 1 if r["files_over_threshold"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        sys.stderr.write(f"classifier: {e}\n")
        sys.exit(1)
