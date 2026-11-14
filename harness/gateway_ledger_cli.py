"""gateway_ledger_cli.py -- `flywheel gateway-ledger`: read and check the gateway's record.

  flywheel gateway-ledger verify             check every segment; exit 0 only when all hold
  flywheel gateway-ledger show [--key NAME] [--kind KIND] [--last N] [--json]
                                             list entries, oldest first

The gateway appends one entry per model call to a hash-chained ledger under
the Flywheel home (`gateway-ledger/`). `verify` recomputes every hash and
link, checks each segment against the one before it and the last segment
against the head record, and names what is wrong. `show --key NAME` lists the
calls of one gateway key; `--key owner` lists calls made with the gateway
token, which includes entries that name no key. `show` also exits 1 when the
ledger does not verify, after printing the entries that do.

Both commands only read. They can run while the gateway is running.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from harness import gateway_ledger

USAGE = __doc__.split("\n\n", 1)[1].rstrip()
OWNER = "owner"
RETRY_AFTER = 0.25                      # seconds before `_checked` reads a second time
_CONTROL = {code: f"\\x{code:02x}" for code in [*range(32), 127]}


def _home(environ=None) -> str:
    from harness.lane_workdir import flywheel_home
    return str(flywheel_home(os.environ if environ is None else environ))


def _checked(home) -> list:
    """`gateway_ledger.check`, read once more when the first read finds a problem.

    A running gateway appends while this reads: a line can be half written,
    and the head record can be ahead of the segment that was read just before
    it. A second read a moment later settles both. A ledger that is broken on
    disk is broken on the second read too."""
    found = gateway_ledger.check(home)
    if all(segment["ok"] for segment in found):
        return found
    time.sleep(RETRY_AFTER)
    return gateway_ledger.check(home)


def render_verify(found: list) -> tuple:
    """(text, ok) for the result of `gateway_ledger.check`."""
    if not found:
        return "no gateway ledger yet: the gateway has recorded no call in this home", True
    lines, ok = [], True
    for segment in found:
        header = segment["header"]
        if header.get("previous_state") == "broken":
            ok = False
            lines.append(f"  {segment['name']}  records a break in "
                         f"{header.get('previous') or 'the ledger before it'}: "
                         f"{header.get('reason')}")
        state = "ok" if segment["ok"] else f"BROKEN: {segment['problem']}"
        ok = ok and segment["ok"]
        lines.append(f"  {segment['name']}  {segment['entries']} entries  "
                     f"head {segment['head'][:16]}  {state}")
    total = sum(segment["entries"] for segment in found)
    lines.append(f"gateway ledger {'verifies' if ok else 'DOES NOT VERIFY'}: "
                 f"{total} entries that verify in {len(found)} segment(s)")
    return "\n".join(lines), ok


def rows(found: list, key=None, kind=None, last=None) -> list:
    """Entries as dicts with their segment, filtered, oldest first."""
    out = []
    for segment in found:
        for entry in segment["rows"]:
            caller = entry.meta.get("key", OWNER)
            if (key is None or caller == key) and (kind is None or entry.kind == kind):
                out.append({"segment": segment["name"], "seq": entry.seq, "kind": entry.kind,
                            "content": entry.content, "meta": entry.meta,
                            "entry_hash": entry.entry_hash})
    return out[-last:] if last else out


def _plain(value) -> str:
    """A value as `show` prints it: control and non-ASCII characters escaped, so a
    model name or reason an upstream chose cannot write to the operator's terminal."""
    return str(value).encode("ascii", "backslashreplace").decode("ascii").translate(_CONTROL)


def _line(row: dict) -> str:
    meta = row["meta"]
    parts = [f"{_plain(row['segment'])[8:14]}:{row['seq']:<6}", f"{_plain(row['kind']):<22}",
             f"key={_plain(meta.get('key', OWNER))}"]
    for name in ("interface", "model_ref", "endpoint", "reason", "charged_tokens",
                 "response_sha"):
        if name in meta and not (name == "endpoint" and "model_ref" in meta):
            parts.append(f"{name}={_plain(meta[name])}")
    return "  ".join(parts)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flywheel gateway-ledger", description=USAGE,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    verbs = parser.add_subparsers(dest="verb")
    verbs.add_parser("verify", help="check every segment; exit 0 only when all hold")
    show = verbs.add_parser("show", help="list entries, oldest first")
    show.add_argument("--key", default=None, help="only the calls of this gateway key, "
                      "or `owner` for the gateway token")
    show.add_argument("--kind", default=None, help="only entries of this kind, for example "
                      "endpoint_call or endpoint_call_failed")
    show.add_argument("--last", type=int, default=None, help="only the newest N")
    show.add_argument("--json", action="store_true", help="one JSON object per line")
    return parser


def main(argv: "list[str] | None" = None, *, environ=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("usage: flywheel gateway-ledger <command>\n" + USAGE,
              file=sys.stdout if argv else sys.stderr)
        return 0 if argv else 2
    args = _parser().parse_args(argv)
    found = _checked(_home(environ))
    text, ok = render_verify(found)
    if args.verb == "verify":
        print(text)
        return 0 if ok else 1
    for row in rows(found, args.key, args.kind, args.last):
        print(json.dumps(row, ensure_ascii=False, sort_keys=True) if args.json else _line(row))
    if not ok:
        print(text, file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
