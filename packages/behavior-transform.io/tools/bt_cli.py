#!/usr/bin/env python3
"""Unified CLI for the behavior-transform surface.

Dispatches to subcommands that exercise each subsystem. Designed for
operator ergonomics: one entry point, tab-completable subcommands,
consistent JSON output when requested.

Entry point: bt (pyproject.toml console_scripts)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _cmd_validate(args: argparse.Namespace) -> int:
    from validate import validate
    report = validate(args.text)
    if args.json:
        sys.stdout.write(report.to_json() + "\n")
    else:
        sys.stdout.write(report.summary() + "\n")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    from subsystem_doctor import run_doctor
    subset = args.check if args.check else None
    report = run_doctor(subset=subset)
    if args.json:
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
    else:
        sys.stdout.write(report.summary() + "\n")
    return 0


def _cmd_transform(args: argparse.Namespace) -> int:
    from transform import transform_text
    result = transform_text(
        args.text,
        mode=args.mode,
        include_framing=not args.no_frame,
    )
    if args.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
    else:
        sys.stdout.write(result.summary() + "\n")
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    from pipeline import PreInferencePipeline
    pipe = PreInferencePipeline()
    result = pipe.run(args.text)
    if args.json:
        sys.stdout.write(result.to_json() + "\n")
    else:
        lines = [
            f"Pressure: {result.pressure.label} ({result.pressure.score})",
            f"Policy:   {result.policy.decision}",
            f"Friction: {result.friction_probability}",
            f"Blocked:  {result.blocked}",
        ]
        if result.classification.category != "unclassified":
            lines.append(f"Category: {result.classification.category}")
        sys.stdout.write("\n".join(lines) + "\n")
    return 0


def _cmd_modulate(args: argparse.Namespace) -> int:
    from semantic_modulator import semantic_modulator
    mod = semantic_modulator()
    result = mod.modulate(args.text)
    if args.json:
        sys.stdout.write(json.dumps({
            "original": result.original,
            "modulated": result.modulated,
            "framing_injected": result.framing_injected,
            "compound_rewrites": result.compound_rewrites,
            "technique_mappings": len(result.technique_mappings),
        }, indent=2) + "\n")
    else:
        if result.modulated == result.original:
            sys.stdout.write("No modulation needed (clean text).\n")
        else:
            sys.stdout.write(result.modulated + "\n")
    return 0


def _cmd_calibrate(args: argparse.Namespace) -> int:
    from prose_vocabulary_map import apply_calibration
    result, count = apply_calibration(args.text)
    if args.json:
        sys.stdout.write(json.dumps({
            "original": args.text,
            "calibrated": result,
            "substitution_count": count,
        }, indent=2) + "\n")
    else:
        if count == 0:
            sys.stdout.write("No calibrations applied (clean text).\n")
        else:
            sys.stdout.write(f"[{count} substitutions]\n{result}\n")
    return 0


def _cmd_adaptive(args: argparse.Namespace) -> int:
    from adaptive_modulator import adaptive_modulate
    result = adaptive_modulate(
        args.text,
        max_passes=args.max_passes,
    )
    if args.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
    else:
        lines = [
            f"Adaptive ({result.total_passes} pass{'es' if result.total_passes != 1 else ''}):",
            f"  Obfuscation: {result.obfuscation_detected}",
            f"  Density: {result.density.density_ratio:.1%} (level {result.density.escalation_level})",
            f"  Changes: {result.total_changes}",
        ]
        if result.changed:
            lines.append(f"  Result: {result.modulated[:120]}")
        else:
            lines.append("  No modulation needed (clean text).")
        sys.stdout.write("\n".join(lines) + "\n")
    return 0


def _cmd_discover(args: argparse.Namespace) -> int:
    from term_discover import discover
    paths = [Path(p) for p in args.paths] if args.paths else [Path.cwd()]
    results = discover(paths, min_count=args.min_count)
    if args.json:
        sys.stdout.write(json.dumps(results, indent=2) + "\n")
    else:
        if not results:
            sys.stdout.write("No uncalibrated terms found.\n")
        else:
            sys.stdout.write(f"Found {len(results)} uncalibrated term(s):\n")
            for r in results[:20]:
                sys.stdout.write(
                    f"  [{r['category']:>16}] {r['term']!r} (x{r['count']})\n"
                )
    return 0


def _cmd_normalize(args: argparse.Namespace) -> int:
    from adaptive_modulator import normalize_obfuscation
    normalized, changes = normalize_obfuscation(args.text)
    if args.json:
        sys.stdout.write(json.dumps({
            "original": args.text,
            "normalized": normalized,
            "changes": changes,
            "obfuscation_detected": changes > 0,
        }, indent=2) + "\n")
    else:
        if changes == 0:
            sys.stdout.write("No obfuscation detected.\n")
        else:
            sys.stdout.write(f"[{changes} normalizations]\n{normalized}\n")
    return 0


def _cmd_density(args: argparse.Namespace) -> int:
    from adaptive_modulator import analyze_density
    profile = analyze_density(args.text)
    if args.json:
        sys.stdout.write(json.dumps({
            "total_tokens": profile.total_tokens,
            "sensitive_tokens": profile.sensitive_tokens,
            "density_ratio": round(profile.density_ratio, 4),
            "escalation_level": profile.escalation_level,
            "needs_deep_pass": profile.needs_deep_pass,
        }, indent=2) + "\n")
    else:
        sys.stdout.write(
            f"Density: {profile.density_ratio:.1%} "
            f"({profile.sensitive_tokens}/{profile.total_tokens} sensitive) "
            f"level={profile.escalation_level}\n"
        )
    return 0


def _cmd_mode(args: argparse.Namespace) -> int:
    from io_state import env_mode, env_profile
    mode = env_mode()
    profile = env_profile()
    if args.json:
        sys.stdout.write(json.dumps({"mode": mode, "profile": profile}) + "\n")
    else:
        sys.stdout.write(f"mode={mode}  profile={profile}\n")
    return 0


def _cmd_classify(args: argparse.Namespace) -> int:
    from ml_category_scorer import score_categories
    from ml_hedge_scorer import score_hedging
    result_cat = score_categories(args.text)
    result_hedge = score_hedging(args.text)
    if args.json:
        sys.stdout.write(json.dumps({
            "categories": result_cat.to_dict(),
            "hedging": result_hedge.to_dict(),
        }, indent=2) + "\n")
    else:
        sys.stdout.write(f"Category: {result_cat.top_category} ({result_cat.top_score:.1%})\n")
        for s in result_cat.scores[:3]:
            if s.score > 0.05:
                sys.stdout.write(f"  {s.category}: {s.score:.1%}\n")
        sys.stdout.write(f"Hedge score: {result_hedge.overall_score:.1%}\n")
        for span in result_hedge.spans[:3]:
            sys.stdout.write(f"  [{span.label}] {span.text[:50]}\n")
    return 0


def _cmd_authority(args: argparse.Namespace) -> int:
    from env_authority import resolve_authority
    grant = resolve_authority(surface=args.surface or None)
    if args.json:
        sys.stdout.write(json.dumps(grant.to_dict(), indent=2) + "\n")
    else:
        sys.stdout.write(f"Status: {grant.status}\n")
        sys.stdout.write(f"Surface: {grant.surface}\n")
        sys.stdout.write(f"Operator: {grant.operator_fingerprint[:12] or 'none'}...\n")
        sys.stdout.write(f"Machine: {grant.machine_fingerprint}\n")
        sys.stdout.write(f"Seal: {grant.seal_status}\n")
        sys.stdout.write(f"Valid: {grant.valid}\n")
        if grant.entitlements:
            sys.stdout.write(f"Entitlements: {', '.join(grant.entitlements)}\n")
    return 0 if grant.valid else 1


def _cmd_audit(args: argparse.Namespace) -> int:
    from authority_audit import audit_summary, read_audit_log
    if args.recent:
        entries = read_audit_log(limit=args.limit, gate=args.gate_filter or None)
        if args.json:
            sys.stdout.write(json.dumps(entries, indent=2) + "\n")
        else:
            if not entries:
                sys.stdout.write("No audit entries found.\n")
            else:
                for e in entries:
                    verdict = "ALLOW" if e.get("allowed") else "DENY"
                    sys.stdout.write(
                        f"[{verdict}] {e.get('gate','?')}:{e.get('entitlement','?')} "
                        f"{e.get('reason','')}\n"
                    )
    else:
        summary = audit_summary()
        if args.json:
            sys.stdout.write(json.dumps(summary, indent=2) + "\n")
        else:
            sys.stdout.write(f"Total: {summary['total']} "
                             f"(allowed={summary['allowed']}, denied={summary['denied']})\n")
            if summary.get("gates"):
                for g, counts in summary["gates"].items():
                    sys.stdout.write(f"  {g}: {counts}\n")
    return 0


def _cmd_gate(args: argparse.Namespace) -> int:
    from authority_gate import check_entitlement
    token = args.session_token or None
    result = check_entitlement(args.entitlement, gate=args.gate or "cli",
                               session_token=token)
    if args.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
    else:
        verdict = "ALLOWED" if result.allowed else "DENIED"
        sys.stdout.write(f"{verdict}: {result.entitlement} ({result.reason})\n")
    return 0 if result.allowed else 1


def _cmd_watchdog(args: argparse.Namespace) -> int:
    from env_watchdog import check
    report = check(
        surface=args.surface or None,
        auto_invalidate=not args.dry_run,
        auto_revoke_sessions=not args.dry_run,
    )
    if args.json:
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
    else:
        sys.stdout.write(report.summary() + "\n")
    return 1 if report.has_critical else 0


def _cmd_session(args: argparse.Namespace) -> int:
    from session_authority import (
        create_session, validate_session, revoke_session,
        list_sessions, cleanup_expired, refresh_session,
    )
    if args.action == "create":
        session = create_session(surface=args.surface or None, ttl=args.ttl)
        if args.json:
            sys.stdout.write(json.dumps(session.to_dict(), indent=2) + "\n")
        else:
            sys.stdout.write(f"Session created: {session.token[:16]}...\n")
            sys.stdout.write(f"  Surface: {session.surface}\n")
            sys.stdout.write(f"  Active: {session.active}\n")
            sys.stdout.write(f"  Entitlements: {', '.join(session.entitlements)}\n")
        return 0 if session.active else 1

    if args.action == "validate":
        if not args.token:
            sys.stderr.write("--token required for validate\n")
            return 1
        session = validate_session(args.token)
        if session is None:
            sys.stdout.write("Session not found.\n")
            return 1
        if args.json:
            sys.stdout.write(json.dumps(session.to_dict(), indent=2) + "\n")
        else:
            status = "ACTIVE" if session.active else "INACTIVE"
            if session.revoked:
                status = f"REVOKED ({session.revoke_reason})"
            sys.stdout.write(f"{status}: {session.token[:16]}...\n")
            sys.stdout.write(f"  Gate checks: {session.gate_checks}\n")
            sys.stdout.write(f"  Infer count: {session.infer_count}\n")
        return 0 if session.active else 1

    if args.action == "revoke":
        if not args.token:
            sys.stderr.write("--token required for revoke\n")
            return 1
        session = revoke_session(args.token, reason=args.reason or "cli_revoked")
        if session is None:
            sys.stdout.write("Session not found.\n")
            return 1
        sys.stdout.write(f"Revoked: {session.token[:16]}...\n")
        return 0

    if args.action == "refresh":
        if not args.token:
            sys.stderr.write("--token required for refresh\n")
            return 1
        session = refresh_session(args.token)
        if session is None:
            sys.stdout.write("Session not found.\n")
            return 1
        status = "ACTIVE" if session.active else "REVOKED" if session.revoked else "EXPIRED"
        sys.stdout.write(f"{status}: {session.token[:16]}...\n")
        return 0 if session.active else 1

    if args.action == "list":
        sessions = list_sessions(
            active_only=args.active_only,
            surface=args.surface or None,
        )
        if args.json:
            sys.stdout.write(json.dumps(
                [s.to_dict() for s in sessions], indent=2) + "\n")
        else:
            if not sessions:
                sys.stdout.write("No sessions found.\n")
            else:
                for s in sessions:
                    status = "ACTIVE" if s.active else "revoked" if s.revoked else "expired"
                    sys.stdout.write(
                        f"  [{status:>7}] {s.token[:12]}... "
                        f"surface={s.surface} gates={s.gate_checks} "
                        f"infers={s.infer_count}\n"
                    )
        return 0

    if args.action == "cleanup":
        count = cleanup_expired(max_age_seconds=args.max_age)
        sys.stdout.write(f"Cleaned up {count} expired session(s).\n")
        return 0

    sys.stderr.write(f"Unknown action: {args.action}\n")
    return 1


def _cmd_policy(args: argparse.Namespace) -> int:
    from authority_policy import policy_engine, evaluate_policy
    from env_authority import resolve_authority

    if args.action == "list":
        engine = policy_engine()
        if args.json:
            sys.stdout.write(json.dumps(engine.to_dict(), indent=2) + "\n")
        else:
            rules = engine.rules
            if not rules:
                sys.stdout.write("No policy rules configured.\n")
            else:
                sys.stdout.write(f"{len(rules)} policy rule(s):\n")
                for r in rules:
                    sys.stdout.write(
                        f"  [{r.rule_type}] {r.name}: "
                        f"{r.entitlement} {r.config}\n"
                    )
        return 0

    if args.action == "check":
        if not args.entitlement:
            sys.stderr.write("--entitlement required for check\n")
            return 1
        grant = resolve_authority(surface=args.surface or None)
        verdict = evaluate_policy(args.entitlement, grant)
        if args.json:
            sys.stdout.write(json.dumps(verdict.to_dict(), indent=2) + "\n")
        else:
            status = "ALLOWED" if verdict.allowed else "DENIED"
            sys.stdout.write(f"{status}: {verdict.entitlement}\n")
            sys.stdout.write(
                f"  Rules: {verdict.rules_passed}/{verdict.rules_evaluated} passed\n"
            )
            if not verdict.allowed:
                sys.stdout.write(
                    f"  Denied by: {verdict.denial_rule} ({verdict.denial_reason})\n"
                )
        return 0 if verdict.allowed else 1

    sys.stderr.write(f"Unknown action: {args.action}\n")
    return 1


def _cmd_intel(args: argparse.Namespace) -> int:
    from intel_trends import analyze_trends
    report = analyze_trends(provider=args.provider or "")
    if args.json:
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
    else:
        sys.stdout.write(report.summary() + "\n")
    return 0


def _cmd_infer(args: argparse.Namespace) -> int:
    from inference_loop import InferenceLoop
    from apparatus.gateway import ModelGateway

    gw = ModelGateway(args.backend)

    def send_fn(system, messages):
        resp = gw.chat(args.model, messages, system=system)
        for block in resp.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
        for choice in resp.get("choices", []):
            msg = choice.get("message", {})
            if isinstance(msg.get("content"), str):
                return msg["content"]
        return ""

    loop = InferenceLoop(send_fn, max_level=args.max_level)
    result = loop.run(args.text, [])

    if args.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
    else:
        if result.succeeded:
            sys.stdout.write(result.response + "\n")
        else:
            sys.stdout.write(f"FAILED after {len(result.attempts)} attempts\n")
            sys.stdout.write(result.response + "\n")
    return 0 if result.succeeded else 1


def _cmd_status(args: argparse.Namespace) -> int:
    from behavior_flagship import status_envelope
    result = status_envelope()
    if args.json:
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
    else:
        sys.stdout.write(f"  verdict: {result.get('verdict', 'unknown')}\n")
        for output in result.get("outputs", []):
            sys.stdout.write(f"  {output.get('kind', '')}: root={output.get('root_sha256_prefix', 'n/a')}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bt",
        description="behavior-transform: unified pre/post inference governance CLI",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    sub = parser.add_subparsers(dest="command")

    # validate
    p = sub.add_parser("validate", help="Run text through all layers and report")
    p.add_argument("text", help="Input text to validate")
    p.set_defaults(func=_cmd_validate)

    # doctor
    p = sub.add_parser("doctor", help="22-check subsystem health verification")
    p.add_argument("--check", nargs="*", help="Run specific checks only")
    p.set_defaults(func=_cmd_doctor)

    # transform
    p = sub.add_parser("transform", help="Full-stack semantic transform")
    p.add_argument("text", help="Input text to transform")
    p.add_argument("--mode", choices=["full", "cyber", "prose"], default="full")
    p.add_argument("--no-frame", action="store_true", help="Skip framing injection")
    p.set_defaults(func=_cmd_transform)

    # scan
    p = sub.add_parser("scan", help="Pre-inference pipeline scan")
    p.add_argument("text", help="Input text to scan")
    p.set_defaults(func=_cmd_scan)

    # modulate
    p = sub.add_parser("modulate", help="Apply semantic modulation")
    p.add_argument("text", help="Input text to modulate")
    p.set_defaults(func=_cmd_modulate)

    # calibrate
    p = sub.add_parser("calibrate", help="Apply prose vocabulary calibration")
    p.add_argument("text", help="Input text to calibrate")
    p.set_defaults(func=_cmd_calibrate)

    # adaptive
    p = sub.add_parser("adaptive", help="Adaptive multi-pass modulation with obfuscation detection")
    p.add_argument("text", help="Input text to modulate")
    p.add_argument("--max-passes", type=int, default=3, help="Max modulation passes (1-5)")
    p.set_defaults(func=_cmd_adaptive)

    # discover
    p = sub.add_parser("discover", help="Find uncalibrated vocabulary in the codebase")
    p.add_argument("paths", nargs="*", help="Paths to scan (default: cwd)")
    p.add_argument("--min-count", type=int, default=1, help="Min occurrences to report")
    p.set_defaults(func=_cmd_discover)

    # normalize
    p = sub.add_parser("normalize", help="Detect and remove obfuscation (leetspeak, homoglyphs, spacing)")
    p.add_argument("text", help="Input text to normalize")
    p.set_defaults(func=_cmd_normalize)

    # density
    p = sub.add_parser("density", help="Analyze semantic density of input text")
    p.add_argument("text", help="Input text to analyze")
    p.set_defaults(func=_cmd_density)

    # classify (ML)
    p = sub.add_parser("classify", help="Statistical category + hedge classification (ML)")
    p.add_argument("text", help="Text to classify")
    p.set_defaults(func=_cmd_classify)

    # authority
    p = sub.add_parser("authority", help="Resolve and display environment-native authorization state")
    p.add_argument("--surface", default="", help="Override surface for resolution")
    p.set_defaults(func=_cmd_authority)

    # gate
    p = sub.add_parser("gate", help="Check a specific entitlement gate")
    p.add_argument("entitlement", help="Entitlement to check (transform, infer, inoculate, etc.)")
    p.add_argument("--gate", default="", help="Gate name for audit trail")
    p.add_argument("--session-token", default="", help="Session token to validate before checking the gate")
    p.set_defaults(func=_cmd_gate)

    # audit
    p = sub.add_parser("audit", help="Authority audit log viewer")
    p.add_argument("--recent", action="store_true", help="Show recent entries instead of summary")
    p.add_argument("--limit", type=int, default=20, help="Max entries to show")
    p.add_argument("--gate-filter", default="", help="Filter by gate name")
    p.set_defaults(func=_cmd_audit)

    # watchdog
    p = sub.add_parser("watchdog", help="Environment state change detection")
    p.add_argument("--surface", default="", help="Surface to check")
    p.add_argument("--dry-run", action="store_true", help="Detect only, do not invalidate or revoke")
    p.set_defaults(func=_cmd_watchdog)

    # session
    p = sub.add_parser("session", help="Session authority management")
    p.add_argument("action", choices=["create", "validate", "revoke", "refresh", "list", "cleanup"],
                   help="Session action")
    p.add_argument("--token", default="", help="Session token")
    p.add_argument("--surface", default="", help="Surface filter or override")
    p.add_argument("--ttl", type=int, default=1800, help="Session TTL in seconds")
    p.add_argument("--reason", default="", help="Revocation reason")
    p.add_argument("--active-only", action="store_true", help="List only active sessions")
    p.add_argument("--max-age", type=int, default=86400, help="Max age for cleanup (seconds)")
    p.set_defaults(func=_cmd_session)

    # policy
    p = sub.add_parser("policy", help="Authority policy engine")
    p.add_argument("action", choices=["list", "check"], help="Policy action")
    p.add_argument("--entitlement", default="", help="Entitlement to check")
    p.add_argument("--surface", default="", help="Surface override")
    p.set_defaults(func=_cmd_policy)

    # intel
    p = sub.add_parser("intel", help="Provider intelligence trends and analytics")
    p.add_argument("--provider", default="", help="Filter to specific provider")
    p.set_defaults(func=_cmd_intel)

    # infer
    p = sub.add_parser("infer", help="Closed-loop inference with escalating recovery")
    p.add_argument("text", help="Input text to send through the inference loop")
    p.add_argument("--backend", default="anthropic", help="Model backend")
    p.add_argument("--model", default="claude-sonnet-4-20250514", help="Model ID")
    p.add_argument("--max-level", type=int, default=5, help="Max recovery level (1-5)")
    p.set_defaults(func=_cmd_infer)

    # mode
    p = sub.add_parser("mode", help="Show current IO mode and profile")
    p.set_defaults(func=_cmd_mode)

    # status
    p = sub.add_parser("status", help="Full surface status")
    p.set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
