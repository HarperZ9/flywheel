"""cli.py -- `flywheel monitor gate <adapter>` and `flywheel monitor gate-verify <result>`.

gate         run a text monitor over the frozen gate set, run the planted controls,
             print both error rates with Wilson intervals and the UNVERIFIABLE rate,
             and write the receipted result. Exit 0 ADMIT, 1 REFUSE, 3 UNVERIFIABLE,
             2 for a usage error. --sign-key signs the receipt with an OpenSSH
             Ed25519 key (the `signing` extra); without it the result says UNSIGNED.
gate-verify  re-derive a result from its records and the pinned gate set and check
             its signature. Exit 0 MATCH, 3 UNANCHORED or UNSIGNED, 1 MISMATCH.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

COMMANDS = ("gate", "gate-verify")
_EXIT = {"ADMIT": 0, "REFUSE": 1, "UNVERIFIABLE": 3}


def register(sub) -> None:
    pg = sub.add_parser("gate", help="admission gate for a text monitor")
    pg.add_argument("adapter", help="planted:<name>, ollama:<model> or py:<module>:<callable>")
    pg.add_argument("--endpoint", default="", help="Ollama base URL (required for ollama:)")
    pg.add_argument("--sign-key", dest="sign_key", default="", help="OpenSSH Ed25519 private key")
    pg.add_argument("--weights-digest", dest="weights_digest", default="")
    pg.add_argument("--out", default="", help="result path (default ./monitor-gate-<adapter>.json)")
    pg.add_argument("--json", action="store_true")
    pv = sub.add_parser("gate-verify", help="re-derive and check a gate result")
    pv.add_argument("result")
    pv.add_argument("--trust-root", dest="trust_root", default="",
                    help="signer public key, hex (else FLYWHEEL_SIGNER_PUBKEY)")


def _summary(result: dict) -> str:
    lines = [f"verdict {result['verdict']}" + (f" ({result['reason']})" if result["reason"] else "")]
    for side, b in result["sides"].items():
        lines.append(f"{side:16} {b['rate_name']:16} {b['errors']}/{b['n']} = {b['rate']} "
                     f"[{b['lower']}, {b['upper']}] bar upper < {b['bar_upper_lt']}  "
                     f"YES {b['yes']} NO {b['no']} UNVERIFIABLE {b['unverifiable']} "
                     f"invalid {b['invalid']}")
    lines.append(f"UNVERIFIABLE rate, both sides: {result['unverifiable_rate']}")
    for name, c in result["controls"].items():
        lines.append(f"control {name:20} expected {c['expected']:7} observed {c['observed']:7} "
                     f"{'ok' if c['ok'] else 'FAILED'}")
    return "\n".join(lines) + "\n"


def _gate(args, stdout, stderr) -> int:
    from . import gate_set, monitors, receipt, score
    try:
        gate = gate_set.load()
    except (gate_set.GateSetError, OSError, ValueError) as exc:
        stderr.write(f"gate UNVERIFIABLE: {exc}\n")
        return 3
    key = None
    if args.sign_key:
        from ..receipt_signer import SigningKeyError, load_signing_key
        try:
            key = load_signing_key(args.sign_key)
        except (SigningKeyError, OSError, ImportError) as exc:
            stderr.write(f"cannot load signing key: {exc}\n")
            return 2
    try:
        monitor, descriptor = monitors.resolve(args.adapter, endpoint=args.endpoint,
                                               seed=int(gate.spec["random_seed"]))
    except monitors.MonitorSpecError as exc:
        stderr.write(f"{exc}\n")
        return 2
    control_block = score.controls(gate)
    records = score.run_monitor(gate, monitor)
    result = score.decide(gate, records, control_block)
    doc = receipt.result_document(gate, descriptor, records, result, signing_key=key,
                                  weights_digest=args.weights_digest)
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", args.adapter)[:60]
    out = Path(args.out or f"monitor-gate-{slug}.json")
    out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        stdout.write(json.dumps({k: result[k] for k in ("verdict", "reason", "failed", "sides",
                                                        "unverifiable_rate", "controls")}) + "\n")
    else:
        stdout.write(_summary(result))
    stderr.write(f"wrote {out} ({'signed' if key else 'UNSIGNED'})\n")
    return _EXIT[result["verdict"]]


def _verify(args, stdout, stderr) -> int:
    from .receipt import verify
    root = args.trust_root or os.environ.get("FLYWHEEL_SIGNER_PUBKEY", "").strip()
    try:
        doc = json.loads(Path(args.result).read_text(encoding="utf-8"))
        trust = bytes.fromhex(root) if root else None
    except (OSError, ValueError) as exc:
        stderr.write(f"cannot read result or trust root: {exc}\n")
        return 1
    report = verify(doc, trust_root=trust)
    stdout.write(json.dumps(report) + "\n")
    return {"MATCH": 0, "UNANCHORED": 3, "UNSIGNED": 3}.get(report["status"], 1)


def dispatch(args, stdout, stderr) -> int:
    if args.cmd == "gate":
        return _gate(args, stdout, stderr)
    return _verify(args, stdout, stderr)
