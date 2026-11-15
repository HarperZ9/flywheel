#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.cli -- the unified command line.

  articulate check [FILE ...] [--profile P] [--json] [--gate] [--verbose]
  articulate score [FILE ...] [--profile P]

With no FILE, reads stdin. The profile is chosen by --profile, else an in-file
`writing-profile:` tag, else the file path, else the default. `--gate` exits 1
when any input is blocked under its profile, for CI use.
"""
import argparse
import json
import os
import sys

from . import cli_config, cli_report, modes, profiles, pysource, receipt
from .checkext import check_text
from .detector import binary_reason, ruleset_fingerprint


def _resolve(name, text, args):
    """Return (label, profile_dict). A --mode wins over profile inference, and a
    project config adds its profile globs and rules (articulate.cli_config)."""
    from .cli_config import resolve
    return resolve(name, text, args)


def _redact(r):
    """Strip the content-bearing fields from a result, so no export path carries a
    verbatim substring OR the exact offsets/length that reconstruct it under
    --content-free. Keeps only line, rule_id, tier, and category per finding."""
    def strip(f):
        # label enumerates a closed-vocabulary rule's candidate words, so drop it
        # from content-free output and report the category alone.
        for k in ("match", "snippet", "col", "start", "end", "label"):
            f.pop(k, None)
    for tier in ("high", "medium", "low"):
        for f in r.get(tier, []):
            strip(f)
    for b in r.get("blocks", []):
        b.pop("snippet", None)
        for tier in ("high", "medium", "low"):
            for f in b.get(tier, []):
                strip(f)
    return r


def _prose(name, text):
    """A .py file's prose is its docstrings and comments; extract those, keeping
    line numbers, so the detector does not score code as prose."""
    if name.lower().endswith(".py"):
        return pysource.prose_of(text)
    return text

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

_SARIF_LEVEL = {"HIGH": "error", "MEDIUM": "warning", "LOW": "note"}


def _pkgver():
    try:
        from . import __version__
        return __version__
    except Exception:  # noqa: BLE001
        return "0.0.0"


def to_sarif(results):
    """SARIF 2.1.0 from check results, using the span records. GitHub Code
    Scanning, Azure DevOps, and reviewdog ingest this for inline PR annotations."""
    rules, out = {}, []
    for r in results:
        uri = "stdin" if r["file"] == "<stdin>" else r["file"].replace("\\", "/")
        if uri != "stdin" and os.path.isabs(r["file"]):
            # SARIF wants a URI: an absolute path becomes file:///, a relative
            # path stays a relative reference to the repository root.
            from pathlib import Path
            uri = Path(r["file"]).resolve().as_uri()
        for f in r["high"] + r["medium"] + r.get("low", []):
            rid = f["rule_id"]
            desc = f.get("label") or f["category"]      # category only when redacted
            rules.setdefault(rid, {"id": rid, "name": f["category"],
                                   "shortDescription": {"text": desc}})
            if f.get("match") is not None:
                msg = f"{desc}: {f['match']!r}"
            else:
                msg = f"{desc}" if "label" in f else f"{f['category']} tell"
            # Exact offsets when present, else a line-only locator for a content-free
            # run, so the export never leaks the match length or position.
            if all(k in f for k in ("col", "start", "end")):
                region = {"startLine": f["line"], "startColumn": f["col"],
                          "endColumn": f["col"] + (f["end"] - f["start"]),
                          "charOffset": f["start"], "charLength": f["end"] - f["start"]}
            else:
                region = {"startLine": f["line"]}
            out.append({
                "ruleId": rid,
                "level": _SARIF_LEVEL.get(f["tier"], "note"),
                "message": {"text": msg},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": uri}, "region": region,
                }}],
            })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "Articulate", "version": _pkgver(),
                "informationUri": "https://github.com/HarperZ9/articulate",
                "rules": list(rules.values()),
            }},
            "results": out,
        }],
    }


def _profile_name(path, text, override):
    if override:
        return override
    tag = profiles.declared_profile(text)
    if tag:
        return tag
    if path and path != "<stdin>":
        return profiles.profile_for(path)
    return profiles.DEFAULT


def _decode(data):
    """Decode source bytes to text with line endings canonicalized to LF, so a
    CRLF/LF rewrite of an otherwise-identical file is not read as a change. The same
    decode runs at receipt issuance and at audit reverify, so their text hashes agree
    across operating systems."""
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def _inputs(files):
    """Yield (name, text, reason). A binary or unsupported document is refused with
    a reason and no text, so the caller fails closed and never scans a lossy decode
    of its bytes."""
    if files:
        for p in files:
            try:
                with open(p, "rb") as fh:
                    data = fh.read()
            except OSError as e:
                yield p, None, f"cannot read: {e}"
                continue
            reason = binary_reason(data, name=p)
            if reason:
                yield p, None, reason
            else:
                yield p, _decode(data), None
    else:
        yield "<stdin>", sys.stdin.read(), None


def _print_spans(name, pname, blocks):
    """Per-paragraph verdicts, so an AI-heavy block is flagged in place and one
    aggregate score cannot smear across a whole clean document."""
    flagged = [b for b in blocks if b["gate"] == "blocked" or b["elevated"]]
    print(f"[articulate] {name} [{pname}]: {len(blocks)} span(s), {len(flagged)} flagged")
    for b in blocks:
        if b["gate"] == "blocked" or b["elevated"]:
            mark = "FLAG"
        elif b["verdict"] == "unverifiable":
            mark = " ?? "
        else:
            mark = " ok "
        print(f"  [{mark}] span {b['index']} L{b['start_line']}-{b['end_line']}: "
              f"{b['verdict']}, {cli_report.texture_note(b)} "
              f"({b['counts']['high']}H/{b['counts']['medium']}M): {b.get('snippet', '')[:52]}")


def _print_check(name, pname, r, verbose):
    base = name
    if r.get("verdict") == "unverifiable":
        head = f"[articulate] {base} [{pname}]: unverifiable (below the signal floor)"
    elif r["clean"]:
        head = f"[articulate] {base} [{pname}]: clean"
    else:
        head = (f"[articulate] {base} [{pname}]: {len(r['high'])} high, "
                f"{len(r['medium'])} medium ({r['gate']})")
    print(head + "  " + cli_report.texture_note(r))
    for f in r["high"] + r["medium"]:
        print(cli_report.finding_line(f))
    if verbose and r["low"]:
        for f in r["low"]:
            print(cli_report.finding_line(f, "LOW"))


def _cmd_check(args):
    blocked = False
    refused = False
    payload = []
    for name, text, reason in _inputs(args.files):
        if reason:
            print(f"[articulate] {name}: cannot screen ({reason})", file=sys.stderr)
            refused = True
            continue
        text = _prose(name, text)
        try:
            pname, prof = _resolve(name, text, args)
        except (profiles.ProfileError, modes.ModeError) as e:
            print(f"[articulate] {e}", file=sys.stderr)
            return 2
        r = check_text(text, profile=prof)
        r["file"], r["profile"] = name, pname
        if getattr(args, "spans", False):
            from .checkext import analyze_blocks
            r["blocks"] = analyze_blocks(text, profile=prof)
        if getattr(args, "content_free", False):
            _redact(r)          # no export path carries a verbatim substring
        payload.append(r)
        if r["gate"] == "blocked":
            blocked = True
        if getattr(args, "speak", False) and not args.json and not getattr(args, "sarif", False):
            from . import speech
            print(f"{name}.")
            print(speech.script(r["high"] + r["medium"] + r["low"], text))
        elif not args.json and not getattr(args, "sarif", False):
            if getattr(args, "spans", False):
                _print_spans(name, pname, r["blocks"])
            else:
                _print_check(name, pname, r, args.verbose)
    if getattr(args, "sarif", False):
        print(json.dumps(to_sarif(payload), ensure_ascii=False, indent=2))
    elif args.json:
        print(json.dumps({"results": payload}, ensure_ascii=False, indent=2))
    # Fail closed: an unscreenable input fails the gate and never passes silently.
    return 1 if (args.gate and (blocked or refused)) else 0


def _cmd_receipt(args):
    redact = getattr(args, "redact", "none")
    redact = None if redact in (None, "none") else redact
    # The "who": an explicit --reviewer, else the CI actor, else unrecorded.
    reviewer = getattr(args, "reviewer", None) or os.environ.get("GITHUB_ACTOR") or None
    for name, text, reason in _inputs(args.files):
        if reason:
            print(f"[articulate] {name}: cannot screen ({reason})", file=sys.stderr)
            continue
        rec = cli_config.make_receipt(name, text, args, redact=redact, reviewer=reviewer)
        if rec is None:
            return 2
        rec["file"] = name
        print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


def _cmd_verify(args):
    try:
        with open(args.receipt, encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError) as e:
        print(f"[articulate] cannot read receipt {args.receipt}: {e}", file=sys.stderr)
        return 2
    try:
        with open(args.file, "rb") as fh:
            data = fh.read()
    except OSError as e:
        print(f"[articulate] cannot read {args.file}: {e}", file=sys.stderr)
        return 2
    reason = binary_reason(data, name=args.file)
    if reason:
        print(f"[articulate] cannot screen {args.file}: {reason}", file=sys.stderr)
        return 2
    if isinstance(rec, dict) and str(rec.get("schema", "")).startswith("articulate/corpus-receipt/"):
        from . import cli_corpus
        return cli_corpus.verify(rec, [args.file] + args.more)
    if isinstance(rec, dict) and str(rec.get("schema", "")).startswith("articulate/house-receipt/"):
        from . import cli_house
        return cli_house.verify(rec, args.file)
    text = _decode(data)
    verdict, detail = receipt.verify_receipt(rec, text)
    print(f"[articulate] {verdict}: {detail}")
    return {"Match": 0, "Drift": 1, "Unverifiable": 2}.get(verdict, 2)


def _load_receipts(paths):
    """Yield (path, receipt) for JSON receipts under the given files or directories.
    Non-JSON, unparseable, and non-receipt files are skipped."""
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, names in os.walk(p):
                files.extend(os.path.join(root, n) for n in names if n.endswith(".json"))
        else:
            files.append(p)
    for fp in sorted(files):
        try:
            with open(fp, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and rec.get("schema") in (receipt.SCHEMA, receipt.AUDIT_SCHEMA):
            yield fp, rec


def _within_days(created_at, days):
    """True if an ISO-8601 timestamp falls in the last `days` (a bounded window, so a
    future-dated stamp is not counted). False on any malformed or non-string value, so
    a bad stamp is never counted as recent and never crashes the audit."""
    if not isinstance(created_at, str):
        return False
    from datetime import datetime, timedelta, timezone
    try:
        ts = datetime.fromisoformat(created_at)
    except (ValueError, TypeError):
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return now - timedelta(days=days) <= ts <= now


def _cmd_audit(args):
    """Query a directory of committed receipts locally: recorded verdicts, blocked
    rules, stale-ruleset receipts, recent activity, and (with --reverify) whether
    each receipt still holds against its source. No server, no network."""
    from collections import Counter

    current_fp = ruleset_fingerprint()
    recs = list(_load_receipts(args.paths or ["."]))
    by_gate, by_verdict, blocked_rules, reverify = Counter(), Counter(), Counter(), Counter()
    stale = recent = 0
    missing = []
    for _fp, rec in recs:
        by_gate[rec.get("gate", "?")] += 1
        by_verdict[rec.get("verdict", "?")] += 1
        if rec.get("ruleset_version") != current_fp:
            stale += 1
        if _within_days(rec.get("created_at"), args.days):
            recent += 1
        if rec.get("gate") == "blocked":
            for f in (rec.get("findings") or []):   # `or []` also covers findings: null
                blocked_rules[f.get("rule_id", "?")] += 1
        if args.reverify:
            src = rec.get("file")
            if not src or not os.path.isfile(src):
                reverify["source-missing"] += 1
                missing.append((_fp, src))
                continue
            try:
                with open(src, "rb") as fh:
                    data = fh.read()
            except OSError:            # a race or a permission-denied source is unreadable
                reverify["source-unreadable"] += 1
                continue
            if binary_reason(data, name=src):
                reverify["source-unreadable"] += 1
                continue
            text = _decode(data)
            # A source that changed since screening is a stale receipt (a real gate
            # failure), kept apart from an honest sub-threshold/ruleset Unverifiable.
            if rec.get("text_sha256") != receipt.text_sha256(text):
                reverify["source-changed"] += 1
            else:
                verdict, _ = receipt.verify_receipt(rec, text)
                reverify[verdict] += 1

    summary = {
        "receipts": len(recs),
        "by_gate": dict(by_gate),
        "by_verdict": dict(by_verdict),
        "stale_ruleset": stale,
        f"recent_{args.days}d": recent,
        "blocked_by_rule": dict(blocked_rules.most_common(10)),
    }
    if args.reverify:
        summary["reverify"] = dict(reverify)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"[audit] {len(recs)} receipt(s); "
              f"gate {dict(by_gate)}; verdict {dict(by_verdict)}")
        print(f"[audit] stale-ruleset {stale}; active in last {args.days}d {recent}")
        if blocked_rules:
            top = ", ".join(f"{r} x{n}" for r, n in blocked_rules.most_common(10))
            print(f"[audit] blocked by rule: {top}")
        if args.reverify:
            print(f"[audit] reverify: {dict(reverify)}")
    # Fail closed on a real integrity failure: the source drifted from its receipt,
    # changed since screening, cannot be read, or is not there. A receipt with no
    # source was not re-verified, and a gate that found no receipt verified nothing,
    # so both fail. A sub-threshold or stale-ruleset Unverifiable is informational,
    # never a gate failure.
    bad = (reverify.get("Drift", 0) + reverify.get("source-changed", 0)
           + reverify.get("source-unreadable", 0) + reverify.get("source-missing", 0))
    if not (args.gate and args.reverify):
        return 0
    for fp, src in missing:
        named = f"source {src!r} is not a file under {os.getcwd()}" if src else "names no source"
        print(f"[audit] {fp}: {named}. Run the audit from the folder the receipt's "
              f"path is relative to, restore the source, or remove the receipt.",
              file=sys.stderr)
    if not recs:
        print(f"[audit] no receipt found under {', '.join(args.paths or ['.'])}: "
              f"the gate re-verified nothing.", file=sys.stderr)
        return 1
    return 1 if bad else 0


def _cmd_score(args):
    for name, text, reason in _inputs(args.files):
        if reason:
            print(f"[articulate] {name}: cannot screen ({reason})", file=sys.stderr)
            continue
        text = _prose(name, text)
        try:
            pname, prof = _resolve(name, text, args)
        except (profiles.ProfileError, modes.ModeError) as e:
            print(f"[articulate] {e}", file=sys.stderr)
            return 2
        r = check_text(text, profile=prof)
        print(f"[articulate] {name} [{pname}]: verdict {r['verdict']}, "
              f"texture {r['texture_score']}/100 "
              f"({'elevated' if r['elevated'] else 'low'}{cli_report.score_note(r)}), "
              f"gate {r['gate']} "
              f"[{len(r['high'])}H/{len(r['medium'])}M, {r['cadence']['words']}w]")
    return 0


def _read_edit_file(path):
    with open(path, "rb") as fh:
        data = fh.read()
    reason = binary_reason(data, name=path)
    if reason:
        raise ValueError(f"cannot edit binary input ({reason})")
    return _decode(data)


def _author_text(args):
    path = getattr(args, "author_text", None)
    return _read_edit_file(path) if path else None


def _cmd_edit(args):
    from . import cli_edit, editing, host_edit
    try:
        text = _read_edit_file(args.file)
        if args.cmd == "submit":
            result = host_edit.edit_submit(
                text, _read_edit_file(args.rewrite), args.plan,
                scores=json.loads(args.scores) if args.scores else None,
                model=args.model, author_text=_author_text(args))
        else:
            options = {**cli_config.edit_options(args, text, None if args.mode else
                                                  _profile_name(args.file, text, args.profile)),
                       "is_html": args.is_html or args.file.lower().endswith((".html", ".htm")),
                       "is_tex": args.is_tex or args.file.lower().endswith(".tex")}
            options.update(cli_edit.edit_kwargs(args))
            if args.cmd == "plan":
                result = host_edit.edit_plan(text, goal=args.goal, author_text=_author_text(args), **options)
            else:
                result = editing.run_edit(text, goal=args.cmd, backend=args.backend,
                                          bar=args.bar, passes=args.passes,
                                          timeout=args.timeout, **options)
        if not result.get("ok", False):
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2
        # Host plans need another step; they are JSON even without --json.
        if getattr(args, "out", None) and "text" in result and "plan_id" not in result:
            with open(args.out, "w", encoding="utf-8", newline="") as fh:
                fh.write(result["text"])
        from .cli_process import record_pass
        record_pass(args, result, text)
        print(cli_edit.render(args, result, text))
        return 0
    except (OSError, ValueError) as exc:
        print(f"[articulate] {exc}", file=sys.stderr)
        return 2


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if list(argv[:1]) in (["--version"], ["-V"]):
        print(f"articulate {_pkgver()}")
        return 0
    ap = argparse.ArgumentParser(prog="articulate",
                                 description="Finds writing patterns and shows where they are.")
    ap.add_argument("-V", "--version", action="version", version=f"articulate {_pkgver()}")
    sub = ap.add_subparsers(dest="cmd")
    for cmd in ("plan", "submit", "judge", "fix", "polish"):
        p = sub.add_parser(cmd)
        p.add_argument("file", help="original text file")
        if cmd == "submit":
            p.add_argument("rewrite", help="host rewrite or assessment file")
            p.add_argument("--plan", required=True, help="plan_id returned by plan")
            p.add_argument("--scores", help="JSON with before and after quality scores")
            p.add_argument("--model", help="caller-supplied host model name")
        else:
            p.add_argument("--profile")
            p.add_argument("--mode")
            p.add_argument("--is-html", action="store_true")
            p.add_argument("--is-tex", action="store_true")
            if cmd == "plan":
                p.add_argument("--goal", choices=("fix", "polish", "judge"), default="fix")
            else:
                p.add_argument("--backend", choices=("auto", "host", "sampling", "anthropic",
                                                     "claude-cli", "openai", "ollama", "none"))
                p.add_argument("--bar", type=int, default=4)
                p.add_argument("--passes", type=int, default=3)
                p.add_argument("--timeout", type=float, default=600)
        from . import cli_edit
        cli_edit.add_arguments(p, cmd)
        if cmd in ("plan", "submit"):
            p.add_argument("--author-text", help="a file of your own words the edit may add")
        p.add_argument("--out", help="write accepted text to this file")
        p.add_argument("--json", action="store_true", help="emit result JSON (the editor default)")
    for cmd in ("check", "score", "receipt"):
        p = sub.add_parser(cmd)
        p.add_argument("files", nargs="*")
        p.add_argument("--profile", default=None, help="force a register profile")
        p.add_argument("--mode", default=None,
                       help="a writing mode (domain/articulation, e.g. memo/argue)")
        cli_config.add_argument(p)
        if cmd == "check":
            p.add_argument("--json", action="store_true")
            p.add_argument("--sarif", action="store_true", help="emit SARIF 2.1.0")
            p.add_argument("--gate", action="store_true", help="exit 1 if blocked")
            p.add_argument("--verbose", action="store_true")
            p.add_argument("--spans", action="store_true",
                           help="per-paragraph findings, so one dense paragraph shows in place")
            p.add_argument("--content-free", action="store_true",
                           help="omit every verbatim substring from console/JSON/SARIF output")
            p.add_argument("--speak", action="store_true",
                           help="print the findings as a script to read aloud")
        if cmd == "receipt":
            p.add_argument("--spans", action="store_true",
                           help="record a per-span (per-paragraph) receipt")
            p.add_argument("--redact", choices=["none", "drop", "hash"], default="none",
                           help="content-free audit receipt: drop or hash the matched text")
            p.add_argument("--reviewer", default=None,
                           help="record who screened it (else the CI actor, else unset)")
    pv = sub.add_parser("verify", help="replay a receipt against text")
    pv.add_argument("receipt", help="a receipt JSON file")
    pv.add_argument("file", help="the text file to re-derive against")
    pv.add_argument("more", nargs="*", help="further files for a corpus receipt")
    pa = sub.add_parser("audit", help="query committed receipts locally")
    pa.add_argument("paths", nargs="*", help="receipt files or directories (default: .)")
    pa.add_argument("--days", type=int, default=30, help="recent-activity window")
    pa.add_argument("--reverify", action="store_true",
                    help="replay each receipt against its source file")
    pa.add_argument("--gate", action="store_true",
                    help="with --reverify, exit 1 if any receipt drifts")
    pa.add_argument("--json", action="store_true")
    sub.add_parser("modes", help="list available writing modes")
    from . import cli_campaign, cli_corpus, cli_desk, cli_dialogue, cli_house, cli_negation, cli_process
    from . import cli_devices
    cli_campaign.register(sub)
    cli_devices.register(sub)
    cli_corpus.register(sub)
    cli_dialogue.register(sub)
    cli_negation.register(sub)
    cli_house.register(sub)
    cli_process.register(sub)
    cli_desk.register(sub)
    cli_config.register(sub)
    args = ap.parse_args(argv)
    if getattr(args, "corpus_handler", None):
        return args.corpus_handler(args)
    if args.cmd in ("plan", "submit", "judge", "fix", "polish"):
        return _cmd_edit(args)
    if args.cmd == "check":
        return _cmd_check(args)
    if args.cmd == "score":
        return _cmd_score(args)
    if args.cmd == "receipt":
        return _cmd_receipt(args)
    if args.cmd == "verify":
        return _cmd_verify(args)
    if args.cmd == "audit":
        return _cmd_audit(args)
    if args.cmd == "process":
        return cli_process.cmd_process(args)
    if args.cmd == "disclose":
        return cli_process.cmd_disclose(args)
    if args.cmd == "desk":
        return cli_desk.cmd_desk(args)
    if args.cmd == "modes":
        for m in modes.names():
            print(m)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
