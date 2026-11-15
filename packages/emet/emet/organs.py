#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""
organs.py - perception + impedance for the coherence membrane.

The membrane has eyes and a reflex, never hands. organs.py adds two organs and
no third:
  PERCEPTION - witness artifacts across space (paths) and time (since-anchor):
    watch    <manifest> <path>...   open eyes: anchor + logical stamp
    observe  <manifest> <path>...   report UNCHANGED / DRIFTED / NEW / GONE
    confirm  <manifest> <path>...   witness what an operator action changed
  IMPEDANCE - report the re-derivable FACT of whether a proposed OPERATOR action
    has a clean VCS revert path BEFORE it lands; emit REVERTIBLE / NOT_REVERTIBLE
    plus the revert recipe. This is a FACT (a clean revert path exists), NEVER a
    permission to act. Performs nothing; grants nothing.
    gate     <path>...              pre-action check (clean VCS revert path?)

Invariants (the membrane, unchanged):
  * actuates ZERO. The single actuator is the operator. organs only witness and
    advise. gate never edits, never backs up, never reverts - it reports the
    FACT that the operator already HAS a clean revert path (committed VCS state)
    and records the pre-state hash. The operator VCS is the reversibility; organs
    only report whether it exists. REVERTIBLE is a re-derivable fact, not a
    permission; organs grant nobody the authority to act. Many eyes, one hand,
    the hand is the operator.
  * facts and advice only. Every line is re-derivable; decides no safety question.
"""
import sys, os, json, subprocess, hashlib
from . import verdict
from . import report
from .report import say, emit

def sha(b):
    return hashlib.sha256(b).hexdigest()

def raw(p):
    with open(p, "rb") as f:
        return f.read()

def stamp():
    try:
        o = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        return o.stdout.strip() or "no-head"
    except Exception:
        return "no-git"

def watch(manifest, paths):
    db = {"at": stamp(), "artifacts": {}}
    for p in paths:
        p = os.path.normpath(p)
        if os.path.isfile(p):
            h = sha(raw(p)); db["artifacts"][p] = h
            say("watch " + p + " sha256=" + h)
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, sort_keys=True)
    say("watched=" + str(len(db["artifacts"])) + " at=" + db["at"])
    emit("watch", None, 0, watched=len(db["artifacts"]), at=db["at"])

def observe(manifest, paths):
    if os.path.exists(manifest):
        with open(manifest, encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {"artifacts": {}}
    known = db.get("artifacts", {})
    changed = 0; results = []
    for p in paths:
        p = os.path.normpath(p)
        if not os.path.isfile(p):
            say(verdict.governed(verdict.PERCEPTION, "GONE") + "      " + p); changed += 1
            results.append({"path": p, "perception": "GONE"}); continue
        cur = sha(raw(p)); was = known.get(p)
        if was is None:
            say(verdict.governed(verdict.PERCEPTION, "NEW") + "       " + p); changed += 1
            results.append({"path": p, "perception": "NEW"})
        elif cur == was:
            say(verdict.governed(verdict.PERCEPTION, "UNCHANGED") + " " + p)
            results.append({"path": p, "perception": "UNCHANGED"})
        else:
            say(verdict.governed(verdict.PERCEPTION, "DRIFTED") + "   " + p + " was=" + was[:12] + " now=" + cur[:12]); changed += 1
            results.append({"path": p, "perception": "DRIFTED", "was": was, "now": cur})
    say("since=" + db.get("at", "?") + " changed=" + str(changed))
    # A perceived change (DRIFTED/NEW/GONE) is a NEGATIVE FINDING -> exit 1 (SPEC
    # s.5); all UNCHANGED -> 0. The exit is a fact, never a permission.
    emit("observe", None, 0 if changed == 0 else 1, since=db.get("at", "?"), changed=changed, results=results)

def revertible(p):
    d = os.path.dirname(os.path.abspath(p)) or "."
    try:
        t = subprocess.run(["git", "-C", d, "ls-files", "--error-unmatch", p], capture_output=True, text=True, timeout=10)
        if t.returncode != 0:
            return (False, "untracked - no VCS revert path")
        s = subprocess.run(["git", "-C", d, "status", "--porcelain", "--", p], capture_output=True, text=True, timeout=10)
        if s.stdout.strip():
            return (False, "uncommitted changes - revert ambiguous")
        return (True, "git checkout -- " + os.path.basename(p))
    except Exception as e:
        return (False, "git unavailable: " + type(e).__name__)

def gate(paths):
    say("PRE-ACTION IMPEDANCE GATE (organs perform nothing; the operator acts)")
    revertible_all = True; results = []
    for p in paths:
        p = os.path.normpath(p)
        if os.path.isfile(p):
            pre = sha(raw(p))[:12]; ok, why = revertible(p)
        else:
            pre = "absent"; ok, why = (True, "new file - revert = delete")
        token = verdict.governed(verdict.REVERT, "REVERTIBLE" if ok else "NOT_REVERTIBLE")
        say(token + " " + p + " pre=" + pre + " revert=[" + why + "]")
        results.append({"path": p, "revert": token, "pre": pre, "recipe": why})
        revertible_all = revertible_all and ok
    gate_token = verdict.governed(verdict.REVERT, "REVERTIBLE" if revertible_all else "NOT_REVERTIBLE")
    say("gate=" + gate_token + "  (advisory fact; the operator decides and acts)")
    # NOT_REVERTIBLE is a NEGATIVE FINDING (no clean revert path) -> exit 1 (SPEC
    # s.5), explicitly NOT a denial or permission; the operator decides and acts.
    emit("gate", gate_token, 0 if revertible_all else 1, results=results)

def main():
    a = [x for x in sys.argv if x != "--json"]
    if len(a) != len(sys.argv):
        report.enable_json()
    if   len(a) >= 4 and a[1] == "watch":   watch(a[2], a[3:])
    elif len(a) >= 4 and a[1] == "observe": observe(a[2], a[3:])
    elif len(a) >= 4 and a[1] == "confirm": observe(a[2], a[3:])
    elif len(a) >= 3 and a[1] == "gate":    gate(a[2:])
    else: print(__doc__); sys.exit(64)

if __name__ == "__main__":
    main()
