#!/usr/bin/env python3
"""Fail closed unless the v0.5.2 detector closure and fingerprint are retained.

This is source retention, not a fairness or semantic-quality certification.
The baseline comes from git show 2884ce4:<path>, after verifying the annotated
v0.5.2 tag peels to that commit. Updating this gate requires explicit review;
there is deliberately no --refresh or acceptance-generation command.

The detector imports masking. Its fingerprint imports profiles, genres and
modes, whose local imports close over those modules. Rule tables, thresholds,
profile/genre definitions and masking data are inline in that closure. The
package initializer also executes on import. Only its version assignment may
vary so a future feature release need not weaken detector retention. CRLF is
normalized to Git's LF source. No other byte difference is accepted.

Editor guard changes are intentionally outside this closure: the detector
does not import them. This gate does not qualify callers, transport adapters,
packaged artifacts, Python runtime behavior, or the caller's profile inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

BASELINE_DIGEST = "b737107ccddba201d3deab941fb0f9be14b22c63af0f6f76ec45d89c54aba408"
ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(rb'(?m)^__version__ = "[0-9]+\.[0-9]+\.[0-9]+"$')


def canonical_digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def check(root, baseline_path):
    receipt = {"status": "FAIL", "checked_files": 0, "failures": [],
               "scope": "Checks that each retained ruleset file matches the reviewed "
               "baseline and that the ruleset fingerprint re-derives from those files."}
    failures = receipt["failures"]
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        if canonical_digest(baseline) != BASELINE_DIGEST:
            raise ValueError("baseline digest differs from reviewed release pin")
        receipt.update(baseline_commit=baseline["baseline_commit"],
                       baseline_tag=baseline["baseline_tag"],
                       expected_fingerprint=baseline["ruleset_fingerprint"])
        retained = {}
        for relative, expected in baseline["files"].items():
            path = root / relative
            if path.resolve() != root.resolve() / relative or not path.is_file():
                failures.append(f"{relative}: missing or redirected source")
                continue
            # A same-named package takes precedence over the retained .py file.
            if path.stem != "__init__" and path.with_suffix("").exists():
                failures.append(f"{relative}: package shadow exists")
                continue
            raw = path.read_bytes().replace(b"\r\n", b"\n")
            normalized = raw
            if path.name == "__init__.py":
                normalized, count = VERSION.subn(b'__version__ = "<release-version>"', raw)
                if count != 1:
                    failures.append(f"{relative}: invalid version assignment")
            if hashlib.sha256(normalized).hexdigest() != expected["retained_sha256"]:
                failures.append(f"{relative}: retained bytes differ")
            retained[path.name] = raw
            receipt["checked_files"] += 1
        if failures:
            return receipt
        # Execute only verified source in a fresh stdlib-only process, excluding
        # editable installs, sitecustomize, stale .pyc files and unrelated editors.
        with tempfile.TemporaryDirectory(prefix="articulate-ruleset-") as temp:
            package = Path(temp) / "articulate"
            package.mkdir()
            for name, raw in retained.items():
                (package / name).write_bytes(raw)
            code = ("import sys;sys.path.insert(0,sys.argv[1]);"
                    "from articulate.detector import ruleset_fingerprint;"
                    "print(ruleset_fingerprint())")
            result = subprocess.run([sys.executable, "-I", "-S", "-c", code, temp],
                                    capture_output=True, text=True, timeout=30)
            fingerprint = result.stdout.strip()
            receipt["observed_fingerprint"] = fingerprint
            if result.returncode or fingerprint != baseline["ruleset_fingerprint"]:
                failures.append("isolated ruleset fingerprint differs or failed")
        if not failures:
            receipt["status"] = "PASS"
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        failures.append(f"retention check failed: {exc}")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path,
                        default=Path(__file__).with_name("release_ruleset_baseline.json"))
    args = parser.parse_args()
    receipt = check(args.root, args.baseline)
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
