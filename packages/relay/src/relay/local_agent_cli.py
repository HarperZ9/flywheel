"""local_agent_cli.py — CLI/REPL for the standalone local agent (offline tier).

  python -m relay.local_agent_cli --health          # which local tiers are live?
  python -m relay.local_agent_cli "explain this fn" --file foo.py
  python -m relay.local_agent_cli                    # interactive REPL

Runs entirely on local models (serve.py's trained 14B/32B, or Ollama), with
automatic failover. Prints a per-turn receipt id so even offline turns are
witnessed. No hosted account is touched.
"""
from __future__ import annotations

import argparse
import json
import sys

from .local_agent import (
    BackendError,
    LocalAgent,
    available_backends,
    health_report,
)
from .architect import plan as architect_plan
from .architect import with_plan
from .conventions import with_conventions
from .local_git import commit_run
from .local_loop import run_agent, witnessed_edit_paths
from .local_session import SessionLedger
from .local_tools import ToolExecutor, ToolGate
from .watch import DEFAULT_MARKER, run_watch_once


def _all_backends(args) -> list:
    """Local backends, plus the online provider ladder when --online is set."""
    backends = available_backends(serve_url=args.serve_url, ollama_url=args.ollama_url,
                                  model=args.model)
    if getattr(args, "online", False):
        from .endpoints import build_endpoints
        provs = [p.strip() for p in args.providers.split(",")] if args.providers else None
        backends = backends + build_endpoints(providers=provs)
    return backends


def _build_agent(args) -> LocalAgent:
    agent = LocalAgent(backends=_all_backends(args), prefer=args.backend,
                       max_tokens=args.max_tokens, temperature=args.temperature, seed=args.seed)
    if args.system:
        agent.system = args.system
    return agent


def _context_preamble(paths: list[str]) -> str:
    blocks = []
    for p in paths or []:
        try:
            with open(p, encoding="utf-8") as f:
                blocks.append(f"--- FILE: {p} ---\n{f.read()}")
        except OSError as e:
            blocks.append(f"--- FILE: {p} (unreadable: {e}) ---")
    return ("\n\n".join(blocks) + "\n\n") if blocks else ""


def _emit(resp: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(resp, indent=2))
        return
    text = resp["content"][0]["text"] if resp.get("content") else ""
    rid = resp.get("x_receipt", {}).get("receipt_id", "?")
    print(text)
    print(f"\n[{resp.get('backend', '?')} | receipt {rid}]", file=sys.stderr)


def _live_backend(agent):
    live_backend = getattr(agent, "live_backend", None)
    return live_backend() if callable(live_backend) else None


def _has_send(agent) -> bool:
    return callable(getattr(agent, "send", None))


def _repl(agent: LocalAgent, as_json: bool) -> int:
    live = _live_backend(agent)
    print(f"local-agent REPL — backend: {live.name if live else 'NONE LIVE'} "
          f"(/health, /reset, /exit)", file=sys.stderr)
    while True:
        try:
            line = input("» ").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return 0
        if not line:
            continue
        if line == "/exit":
            return 0
        if line == "/health":
            print(json.dumps(health_report(agent.backends), indent=2), file=sys.stderr)
            continue
        if line == "/reset":
            agent.history.clear()
            print("(history cleared)", file=sys.stderr)
            continue
        try:
            _emit(agent.send(line), as_json)
        except BackendError as e:
            print(f"[error] {e}", file=sys.stderr)


def _coding_agent(args) -> LocalAgent:
    """Build the coding agent with optional project conventions and repo map."""
    agent = _build_agent(args)
    if not hasattr(agent, "system"):
        try:
            agent.system = ""
        except AttributeError:
            return agent
    elif not isinstance(agent.system, str):
        agent.system = str(agent.system or "")

    if not getattr(args, "no_conventions", False):
        agent.system = with_conventions(agent.system, args.root)
    if not getattr(args, "no_repo_map", False):
        from .local_repomap import build_repo_map
        agent.system = (f"{agent.system}\n\nRepo map ({args.root}):\n"
                        f"{build_repo_map(args.root, max_files=20, max_symbols=15)}")
    return agent


def _env_hash(root: str) -> str:
    """A content anchor over the dependency lockfile, so the cert names the env it
    ran in. Absent lockfile -> empty (declared, not re-derived; see cert.py)."""
    import hashlib
    import pathlib
    for name in ("uv.lock", "poetry.lock", "requirements.txt", "pyproject.toml"):
        p = pathlib.Path(root) / name
        if p.exists():
            return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return ""


def _write_cert(args, result) -> None:
    import json as _json

    from .cert import emit_cert
    from .contract import Contract, STRICT
    contract = STRICT
    if args.contract:
        with open(args.contract, encoding="utf-8") as fh:
            contract = Contract.from_dict(_json.load(fh))
    cert = emit_cert(result, contract, env_hash=_env_hash(args.root))
    with open(args.cert, "w", encoding="utf-8") as fh:
        _json.dump(cert, fh)
    print(f"[cert | {cert['verdict']} | wrote {args.cert} | "
          f"verify offline: python verify_cert.py {args.cert}]", file=sys.stderr)


def _stdin_approver():
    """An approve(name, args) that asks the operator on stderr and reads stdin. A
    reply starting with 'y' allows; anything else denies. On EOF (non-interactive
    stdin) it denies, so an unattended --interactive run never auto-approves."""
    import json as _json

    def approve(name, args):
        preview = _json.dumps(args, sort_keys=True)
        if len(preview) > 300:
            preview = preview[:300] + "..."
        sys.stderr.write(f"[approve] {name} {preview}\n  allow? [y/N] ")
        sys.stderr.flush()
        try:
            reply = input()
        except EOFError:
            return False
        return reply.strip().lower().startswith("y")
    return approve


def _run_agentic(args) -> int:
    if not args.prompt:
        print("[error] --agent needs a task prompt", file=sys.stderr)
        return 2
    agent = _coding_agent(args)
    if _live_backend(agent) is None:
        print("[error] no local backend is healthy (start serve.py or ollama)", file=sys.stderr)
        return 1
    if not _has_send(agent):
        print("[error] coding agent is missing send()", file=sys.stderr)
        return 1
    goal = _context_preamble(args.file) + args.prompt
    if args.architect_backend:
        planner = LocalAgent(backends=_all_backends(args), prefer=args.architect_backend,
                             max_tokens=args.max_tokens, temperature=args.temperature,
                             seed=args.seed)
        if _live_backend(planner) is None:
            print(f"[error] --architect backend {args.architect_backend!r} is not healthy",
                  file=sys.stderr)
            return 1
        goal = with_plan(goal, architect_plan(planner, goal))
    executor = ToolExecutor(root=args.root,
                            gate=ToolGate(allow_write=args.allow_write, allow_exec=args.allow_exec))
    ledger = SessionLedger()
    result = run_agent(agent, goal, executor, ledger,
                       max_steps=args.max_steps, check=args.check or None,
                       test_cmd=args.test_cmd or None,
                       approve=_stdin_approver() if getattr(args, "interactive", False) else None,
                       compact_budget=getattr(args, "compact_budget", 0))
    print(result["final"])
    if args.save:
        ledger.save(args.save)
    if args.cert:
        _write_cert(args, result)
    if args.review:
        from .local_review_agent import review_run
        rv = review_run(lambda: _build_agent(args), ledger)
        detail = f" | {rv['findings'][:200]}" if rv.get("reviewed") else " (no edits)"
        print(f"\n[review-agent | {rv['verdict']}{detail}]", file=sys.stderr)
    committed = ""
    if args.auto_commit:
        if result["accepted"]:
            # stage only the files the ledger witnessed as edits, so the commit binds
            # the trajectory rather than any other change in the working tree. Only an
            # ACCEPTED run is committed: a failed check, an unfinished run (max_steps),
            # or a backend death all leave the tree uncommitted on the operator's behalf.
            c = commit_run(args.root, args.prompt, result["checkpoint"],
                           paths=witnessed_edit_paths(ledger))
            committed = (f" | committed {c['sha']}" if c.get("committed")
                         else f" | not committed ({c.get('reason')})")
        else:
            committed = " | not committed (run not accepted)"
    chk = "" if result["check_passed"] is None else f" | check={'pass' if result['check_passed'] else 'FAIL'}"
    # a green check that was gamed by editing the grader is called out, not hidden
    tamper = "" if result.get("check_trusted", True) else \
        f" | check UNTRUSTED ({result['integrity']['flag_count']} integrity flag(s))"
    note = f" | {result['note']}" if result.get("note") else ""
    print(f"\n[agent | {result['steps']} step(s) | {result['entries']} ledger entries | "
          f"verified={result['verified']} | accepted={result['accepted']}{chk}{tamper}{note} | "
          f"checkpoint {result['checkpoint'][:16]}"
          f"{' | saved ' + args.save if args.save else ''}{committed}]", file=sys.stderr)
    # the reviewability projection: what a reviewer checks first, as facts from the ledger
    rv, risk = result["review"], result["risk"]
    demands = len(risk["demands"])
    print(f"[review | reviewability {rv['reviewability']:.2f} | "
          f"edited-unread {len(rv['edited_unread'])} | unverified {len(rv['unverified_edits'])} | "
          f"failed {rv['failed_calls']}"
          f"{f' | {demands} high-risk edit(s) demand a receipt' if demands else ''}]",
          file=sys.stderr)
    # exit 0 iff the run was ACCEPTED (finished, verified, and any requested check
    # passed), so --agent is a sound CI gate: an unfinished run or one whose check
    # never ran is never reported as success.
    return 0 if result["accepted"] else 1


def _run_best_of(args) -> int:
    import copy

    from .verified_bon import select_best
    if not args.prompt:
        print("[error] --best-of needs a task prompt", file=sys.stderr)
        return 2

    def make_agent(seed):
        scoped = copy.copy(args)
        scoped.seed = seed
        return _coding_agent(scoped)

    if _live_backend(make_agent(args.seed)) is None:
        print("[error] no local backend is healthy (start serve.py or ollama)", file=sys.stderr)
        return 1

    def make_executor():
        return ToolExecutor(root=args.root,
                            gate=ToolGate(allow_write=args.allow_write, allow_exec=args.allow_exec))

    sel = select_best(make_agent, _context_preamble(args.file) + args.prompt, make_executor,
                      n=args.best_of, max_steps=args.max_steps, check=args.check or None,
                      base_seed=args.seed)
    win = sel["results"][sel["winner"]]
    print(win["final"])
    if args.save:
        sel["meta_ledger"].save(args.save)
    print(f"\n[best-of-{args.best_of} | winner=run{sel['winner']} | accepted={win['accepted']} | "
          f"selection verified={sel['meta_ledger'].verify()} | order={sel['order']}"
          f"{' | selection saved ' + args.save if args.save else ''}]", file=sys.stderr)
    return 0 if win["accepted"] else 1


def _run_watch(args) -> int:
    import time

    agent = _coding_agent(args)
    if _live_backend(agent) is None:
        print("[error] no local backend is healthy (start serve.py or ollama)", file=sys.stderr)
        return 1
    if not _has_send(agent):
        print("[error] coding agent is missing send()", file=sys.stderr)
        return 1
    # watch mode's whole point is applying the fix in place; exec stays opt-in.
    executor = ToolExecutor(root=args.root, gate=ToolGate(allow_write=True, allow_exec=args.allow_exec))
    print(f"[watch] polling {args.root} every {args.watch_interval}s for '{args.watch_marker}' "
          f"comments (Ctrl-C to stop)", file=sys.stderr)
    try:
        while True:
            for r in run_watch_once(agent, executor, marker=args.watch_marker,
                                    max_steps=args.max_steps):
                print(f"[watch] {r['path']}:{r['line']} \"{r['instruction']}\" -> {r['final']} "
                      f"(verified={r['verified']}, checkpoint {r['checkpoint'][:16]})")
            time.sleep(args.watch_interval)
    except KeyboardInterrupt:
        print("\n[watch] stopped", file=sys.stderr)
        return 0


def _architect_mode_error(args) -> str:
    if not args.architect_backend:
        return ""
    unsupported = []
    if not args.agent:
        unsupported.append("missing --agent")
    if args.watch:
        unsupported.append("--watch")
    if args.probe_injection:
        unsupported.append("--probe-injection")
    if args.mcp:
        unsupported.append("--mcp")
    if args.view:
        unsupported.append("--view")
    if args.verify_cert:
        unsupported.append("--verify-cert")
    if args.bisect:
        unsupported.append("--bisect")
    if args.health:
        unsupported.append("--health")
    if args.best_of and args.best_of > 1:
        unsupported.append("--best-of")
    if not unsupported:
        return ""
    return ("--architect is supported only with plain single-run --agent; "
            "unsupported with " + ", ".join(unsupported))


def _serve_mcp(args) -> int:
    """Serve MCP with the grants of this launch: the flags, or RELAY_ALLOW_WRITE /
    RELAY_ALLOW_EXEC / RELAY_MCP_ROOT. Tool arguments can only narrow them."""
    import os

    from .mcp_grants import describe, grants_from_launch, pin_root
    try:
        grants = pin_root(grants_from_launch(allow_write=args.allow_write,
                                             allow_exec=args.allow_exec, env=os.environ,
                                             root=args.root))
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    print(f"[relay mcp] {describe(grants)}", file=sys.stderr)
    from .local_mcp import serve
    return serve(grants=grants)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="relay", description=__doc__)
    ap.add_argument("prompt", nargs="?", help="one-shot prompt; omit for a REPL")
    ap.add_argument("--health", action="store_true", help="report live local tiers and exit")
    ap.add_argument("--backend", default="auto",
                    help="force a backend by name (auto|serve|ollama|<provider-mode>)")
    ap.add_argument("--model", default="", help="force an Ollama model name")
    ap.add_argument("--file", action="append", default=[], help="inject a file as context (repeatable)")
    ap.add_argument("--system", default="", help="override the system prompt")
    ap.add_argument("--max-tokens", type=int, default=512, dest="max_tokens")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--serve-url", default="http://127.0.0.1:8765", dest="serve_url")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434", dest="ollama_url")
    ap.add_argument("--json", action="store_true", help="print the full response dict")
    # agentic mode
    ap.add_argument("--agent", action="store_true",
                    help="run the prompt as an agentic task with gated tools + a witnessed ledger")
    ap.add_argument("--root", default=None, help="root for file tools read/list/write (--agent; "
                    "default .); with --mcp, the launch root every run stays inside (also "
                    "RELAY_MCP_ROOT); run/exec sets only cwd and is NOT confined to root")
    ap.add_argument("--allow-write", action="store_true", dest="allow_write",
                    help="enable file writes under --root; with --mcp, the most any MCP run "
                    "may do, inside the launch root (also RELAY_ALLOW_WRITE)")
    ap.add_argument("--allow-exec", action="store_true", dest="allow_exec",
                    help="enable the run tool; a shell can write, so this implies --allow-write "
                    "and is not path-confined; with --mcp, the most any MCP run may do "
                    "(also RELAY_ALLOW_EXEC)")
    ap.add_argument("--interactive", action="store_true",
                    help="with --agent, prompt for approval before every mutating tool call "
                    "(write/edit/run); each decision is recorded as a hash-chained approval "
                    "entry bound to the call's bytes, so the .rvc proves a human gated it")
    ap.add_argument("--no-repo-map", action="store_true", dest="no_repo_map",
                    help="skip auto-folding a bounded repo map (--root) into the system prompt "
                    "(--agent/--watch only); the model can still call the repo_map tool itself")
    ap.add_argument("--max-steps", type=int, default=6, dest="max_steps")
    ap.add_argument("--compact-budget", type=int, default=0, dest="compact_budget",
                    help="with --agent, fold older turns once the prompt passes N tokens, "
                    "pinning the task anchor and policy text; each fold is witnessed on the "
                    "ledger with the folded-span and summary hashes (0 = off)")
    ap.add_argument("--best-of", type=int, default=1, dest="best_of",
                    help="with --agent, run the goal N times and select the VERIFIED winner "
                         "(chain intact, check not gamed, integrity clean), not a judge; --save "
                         "writes the hash-chained selection meta-ledger")
    ap.add_argument("--review", action="store_true",
                    help="with --agent, a fresh-context reviewer sees ONLY the diff (not the "
                         "author's ledger) and returns an independent APPROVE/REQUEST_CHANGES")
    ap.add_argument("--check", default="",
                    help="an acceptance command (e.g. \"pytest -q\") run once after the "
                    "agent finishes; the run is accepted only if it passes, --auto-commit "
                    "is skipped on failure, and the exit code is non-zero. Witnessed on the "
                    "ledger. Carries operator authority: runs outside the model's tool gate.")
    ap.add_argument("--test-cmd", default="", dest="test_cmd",
                    help="like --check, but retried: on failure the output is fed back to "
                    "the model and it keeps working until the command passes or --max-steps "
                    "runs out (needs --allow-exec). Shares --check's accept/reject reporting; "
                    "pass at most one of the two.")
    ap.add_argument("--architect", nargs="?", const="auto", default=None, dest="architect_backend",
                    help="with --agent, run a planning turn on the named backend first and "
                    "fold that attributed proposal into the implementer's goal; bare "
                    "--architect uses the first healthy backend")
    ap.add_argument("--save", default="", help="save the session ledger to this JSONL path")
    ap.add_argument("--auto-commit", action="store_true", dest="auto_commit",
                    help="git-commit the changes after an --agent run (existing repo only)")
    ap.add_argument("--stream", action="store_true", help="stream tokens as they arrive (one-shot)")
    ap.add_argument("--online", action="store_true",
                    help="add the online provider ladder (codex/claude/gemini/deepseek)")
    ap.add_argument("--providers", default="",
                    help="comma list to restrict online providers (default: all configured)")
    ap.add_argument("--mcp", action="store_true", help="run as a stdio MCP server")
    ap.add_argument("--view", default="", metavar="LEDGER.jsonl",
                    help="visualize a saved run ledger as a hash-chained trajectory "
                         "(green intact / red broken) with integrity + intent overlays, then exit")
    ap.add_argument("--no-color", action="store_true", dest="no_color",
                    help="with --view, emit a plain-text (byte-stable) timeline")
    ap.add_argument("--cert", default="", metavar="RUN.rvc",
                    help="with --agent, write a proof-carrying .rvc certificate of the run "
                         "(a stranger verifies it offline with verify_cert.py, no model, no re-run)")
    ap.add_argument("--contract", default="", metavar="CONTRACT.json",
                    help="with --cert, the acceptance contract to certify against (default: strict)")
    ap.add_argument("--verify-cert", default="", dest="verify_cert", metavar="RUN.rvc",
                    help="verify a .rvc certificate and print ALLOW/UNVERIFIABLE/REFUTED, then exit")
    ap.add_argument("--bisect", default="", metavar="LEDGER.jsonl",
                    help="git-bisect a saved run: replay its witnessed edits onto --root and "
                         "localize the first edit that breaks --check (needs --root and --check)")
    ap.add_argument("--probe-injection", action="store_true", dest="probe_injection",
                    help="run the defensive prompt-injection robustness probe over the gated tool "
                         "loop and report containment (honors --allow-write/--allow-exec; runs in a "
                         "disposable sandbox, so it never touches the working tree)")
    ap.add_argument("--watch", action="store_true",
                    help="poll --root for a marker comment (default 'RELAY:') in any file, in any "
                         "editor, and act on each as its own witnessed run; the model removes the "
                         "marker itself once done. Implies write access. Ctrl-C to stop.")
    ap.add_argument("--watch-marker", default=DEFAULT_MARKER, dest="watch_marker")
    ap.add_argument("--watch-interval", type=float, default=2.0, dest="watch_interval")
    ap.add_argument("--no-conventions", action="store_true", dest="no_conventions",
                    help="skip auto-including a project AGENTS.md/CONVENTIONS.md in the system "
                         "prompt (--agent/--watch only)")
    args = ap.parse_args(argv)

    architect_error = _architect_mode_error(args)
    if architect_error:
        print(f"[error] {architect_error}", file=sys.stderr)
        return 2

    if args.probe_injection:
        from .injection_probe import probe
        report = probe(allow_write=args.allow_write, allow_exec=args.allow_exec)
        print(json.dumps(report, indent=2))
        return 0 if report["contained"] == report["total"] else 1
    if args.mcp:
        return _serve_mcp(args)
    args.root = args.root or "."
    if args.view:
        from .run_view import load_run, render, verify_edges
        try:
            view = load_run(args.view)
        except (OSError, ValueError) as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
        sys.stdout.write(render(view.ledger, view.result, color=not args.no_color))
        return 0 if all(es.status == "OK" for es in verify_edges(view.ledger)) else 1
    if args.verify_cert:
        import json as _json

        from .cert import verify_cert
        try:
            with open(args.verify_cert, encoding="utf-8") as fh:
                label, detail = verify_cert(_json.load(fh))
        except (OSError, ValueError) as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
        print(f"{label}  {detail}")
        return 0 if label == "ALLOW" else 1
    if args.bisect:
        import json as _json

        from .bisect import bisect_run
        from .local_session import SessionLedger
        if not args.check:
            print("[error] --bisect needs --check (the acceptance command)", file=sys.stderr)
            return 2
        try:
            out = bisect_run(SessionLedger.load(args.bisect, verify=False), args.root, args.check)
        except (OSError, ValueError) as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
        print(_json.dumps(out, indent=2))
        return 0 if out.get("first_bad_seq") is None else 1
    if args.watch:
        return _run_watch(args)
    if args.agent:
        return _run_best_of(args) if args.best_of and args.best_of > 1 else _run_agentic(args)
    if args.health:
        report = health_report(_all_backends(args))
        print(json.dumps(report, indent=2))
        return 0 if report["any_live"] else 1

    agent = _build_agent(args)
    if args.prompt is None:
        return _repl(agent, args.json)
    prompt = _context_preamble(args.file) + args.prompt
    try:
        if args.stream and not args.json:
            resp = agent.stream(prompt, lambda p: (sys.stdout.write(p), sys.stdout.flush()))
            print()
            rid = resp.get("x_receipt", {}).get("receipt_id", "?")
            print(f"[{resp.get('backend', '?')} | receipt {rid}]", file=sys.stderr)
        else:
            _emit(agent.send(prompt), args.json)
    except BackendError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
