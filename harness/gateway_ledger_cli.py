"""gateway_ledger_cli.py -- `flywheel gateway-ledger`: read and check the gateway's record.

  flywheel gateway-ledger verify             check every segment and every call record;
                                             exit 0 only when all hold
  flywheel gateway-ledger show [--key NAME] [--kind KIND] [--last N] [--json] [--full]
                               [--unsettled]  list entries, oldest first
  flywheel gateway-ledger settle CALL [--input N --output N | --no-charge] [--note TEXT]
                                             end an unsettled call by hand

The gateway appends two entries per model call to a hash-chained ledger under
the Flywheel home (`gateway-ledger/`): `endpoint_call_started` before the
provider is contacted, and the call's end entry after. `verify` recomputes
every hash and link, checks each segment against the one before it and the
last segment against the head record, and names what is wrong. It also names
every unsettled call, a started entry with no end entry, which a gateway
leaves when it stops between the two; it then exits 3. And it checks the
call records themselves (gateway_call_audit): an end entry with no started
entry before it, a second end entry for one call, a call id started twice,
and an end entry that differs from its start on the route, the request hash
or the caller are each named, and it then exits 4. `show --key NAME`
lists the calls of one gateway key; `--key owner` lists calls made with the
gateway token, which includes entries that name no key. `show --unsettled`
lists the started entries of unsettled calls. `show` also exits 1 when the
ledger does not verify, after printing the entries that do, 4 when the chain
holds and a call record is at fault, and 3 when it verifies and holds an
unsettled call.

`verify` and `show` only read. They can run while the gateway is running.
`settle` writes one entry, or leaves a request for a running gateway
(gateway_ledger_settle).
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
SHOWN = 50                              # call record faults `verify` prints one by one
WIDTH = 80                              # characters of one field `show` prints without --full
_CONTROL = {code: f"\\x{code:02x}" for code in [*range(32), 127]}


def _home(environ=None) -> str:
    from harness.lane_workdir import flywheel_home
    return str(flywheel_home(os.environ if environ is None else environ))


def _checked(home) -> list:
    """`gateway_ledger.check`, read once more when the first read finds a problem.

    A running gateway appends while this reads. `check` reads the head record
    before the segments, so entries appended in between are more than the
    head names and not a fault. What is left for the second read is a line
    caught half written, or a head record caught mid-rewrite. A ledger that
    is broken on disk is broken on the second read too."""
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


def render_faults(findings: list) -> str:
    """What `verify` says about call records that break the rules. Empty when none do."""
    if not findings:
        return ""
    lines = [f"  CALL RECORD FAULT {code}: call {_plain(call)} at {_plain(where)}: {text}"
             for code, call, where, text in findings[:SHOWN]]
    if len(findings) > SHOWN:
        lines.append(f"  ... and {len(findings) - SHOWN} more")
    lines.append(f"{len(findings)} call record fault(s): the chain of hashes holds and the "
                 "entries do not describe each call as one start followed by one end. A "
                 "gateway does not write such a record")
    return "\n".join(lines)


def rows(found: list, key=None, kind=None, last=None, calls=None, unsettled=False) -> list:
    """Entries as dicts with their segment, filtered, oldest first.

    `calls` is gateway_ledger_settle.unsettled's result: the started entry of
    a call with no end entry gets `state`, "unsettled" or "open"."""
    out, calls = [], calls or {}
    for segment in found:
        for entry in segment["rows"]:
            caller = entry.meta.get("key", OWNER)
            state = (calls.get(entry.content) or {}).get("state") if (
                entry.kind == "endpoint_call_started") else None
            if ((key is None or caller == key) and (kind is None or entry.kind == kind)
                    and (not unsettled or state == "unsettled")):
                out.append({"segment": segment["name"], "seq": entry.seq, "kind": entry.kind,
                            "content": entry.content, "meta": entry.meta,
                            "entry_hash": entry.entry_hash,
                            **({"state": state} if state else {})})
    return out[-last:] if last else out


def _plain(value) -> str:
    """A value as `show` prints it: control and non-ASCII characters escaped, so a
    model name or reason an upstream chose cannot write to the operator's terminal."""
    return str(value).encode("ascii", "backslashreplace").decode("ascii").translate(_CONTROL)


def _json(row: dict) -> str:
    """A row as `show --json` prints it: one JSON object in ASCII.

    Every character outside printable ASCII is a `\\uXXXX` escape, so the C1
    controls (U+0080 to U+009F), the bidi controls and DEL in a recorded string
    cannot write to the operator's terminal. A JSON parser reads the same row."""
    return json.dumps(row, ensure_ascii=True, sort_keys=True).replace("\x7f", "\\u007f")


def _short(value, full: bool) -> str:
    """`_plain(value)`, cut to WIDTH characters with what was left out, unless `full`."""
    text = _plain(value)
    if full or len(text) <= WIDTH:
        return text
    return f"{text[:WIDTH]}...(+{len(text) - WIDTH} more; --full shows all)"


def _line(row: dict, full: bool = False) -> str:
    meta = row["meta"]
    parts = [f"{_plain(row['segment'])[8:14]}:{row['seq']:<6}",
             f"{_short(row['kind'], full):<22}", f"key={_short(meta.get('key', OWNER), full)}"]
    for name in ("interface", "model_ref", "endpoint", "reason", "charged_tokens",
                 "response_sha"):
        if name in meta and not (name == "endpoint" and "model_ref" in meta):
            parts.append(f"{name}={_short(meta[name], full)}")
    if "call" in meta:
        parts.append(f"call={_short(meta['call'], full)}")
    if row.get("state"):
        parts.append("state=UNSETTLED" if row["state"] == "unsettled" else "state=open")
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
    show.add_argument("--full", action="store_true", help="print every field whole; without "
                      f"it a field longer than {WIDTH} characters is cut and says so")
    show.add_argument("--unsettled", action="store_true", help="only the started entries of "
                      "unsettled calls: started, never ended, their gateway gone")
    settle = verbs.add_parser("settle", help="end an unsettled call by hand")
    settle.add_argument("call", help="the call id, from `show --unsettled`")
    settle.add_argument("--input", type=int, default=None, help="input tokens the provider "
                        "billed for the call, charged to its key")
    settle.add_argument("--output", type=int, default=None, help="output tokens it billed")
    settle.add_argument("--no-charge", action="store_true", help="the provider billed nothing")
    settle.add_argument("--note", default="", help="a line kept in the entry")
    return parser


def _settle(args, home) -> int:
    from harness.gateway_ledger_settle import settle
    given = (args.input, args.output)
    counted = given != (None, None)
    if (args.no_charge and counted) or (counted and None in given) or any(
            value is not None and value < 0 for value in given):
        print("give --input N and --output N together (zero or more), or --no-charge",
              file=sys.stderr)
        return 2
    counts = ({"input": 0, "output": 0} if args.no_charge else
              {"input": args.input, "output": args.output} if counted else None)
    text, code = settle(home, args.call, counts, _plain(args.note))
    print(text, file=sys.stdout if code == 0 else sys.stderr)
    return code


def _ignored(home) -> str:
    """One line per file in the ledger folder that is named like a segment and is not one."""
    from harness.gateway_ledger_health import strays
    return "".join(f"  ignored {_plain(name)!r}: its name is not a segment's, so it is not "
                   "part of the ledger\n" for name in strays(gateway_ledger.folder(home)))


def main(argv: "list[str] | None" = None, *, environ=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("usage: flywheel gateway-ledger <command>\n" + USAGE,
              file=sys.stdout if argv else sys.stderr)
        return 0 if argv else 2
    args = _parser().parse_args(argv)
    home = _home(environ)
    if args.verb == "settle":
        return _settle(args, home)
    from harness.gateway_call_audit import faults
    from harness.gateway_ledger_settle import report, unsettled
    found = _checked(home)
    text, ok = render_verify(found)
    calls = unsettled(found, home)
    stuck = any(row["state"] == "unsettled" for row in calls.values())
    wrong = render_faults(faults(found))
    code = 1 if not ok else 4 if wrong else 3 if stuck else 0
    if args.verb == "verify":
        print(_ignored(home) + text + ("\n" + wrong if wrong else "")
              + ("\n" + report(calls) if calls else ""))
        return code
    for row in rows(found, args.key, args.kind, args.last, calls, args.unsettled):
        print(_json(row) if args.json else _line(row, args.full))
    if not ok:
        print(text, file=sys.stderr)
    else:
        for said in (wrong, report(calls) if stuck else ""):
            if said:
                print(said, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
