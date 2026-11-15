#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""
monitor.py - external accountability monitor for the coherence membrane.

Watches a target (a set of files or a baseline manifest) from OUTSIDE, by re-derivation. Trusts
nothing; reports to the operator; decides nothing.

  report   <manifest>   verify every anchored file vs baseline + marker census;
                        DRIFT = change since the operator last authorized.
  reanchor <manifest>   operator authorizes the CURRENT state as the new baseline
                        (re-hash the manifest path set); logged, so every baseline
                        change is itself accounted for.

Baseline policy: the manifest is the operator-signed authorized state. Drift =
unauthorized change. After an authorized change, the operator reanchors; that
event is logged. Every change to the target is therefore either operator-anchored
or flagged - the account stays legible.

Log: monitor_log.jsonl, hash-chained (the accountability history is tamper-evident).
Facts and advice only. Reads raw bytes. Never edits the target.
"""
import sys, os, json, hashlib
from . import corpus
from .report import say, emit, enable_json  # NB: 'report' is a command here, so import the helpers by name
from .verdict import governed, LATTICE, MONITOR_FILE, MONITOR_BASELINE

def sha(b):
    return hashlib.sha256(b).hexdigest()

def _logp(manifest):
    return os.path.join(os.path.dirname(os.path.abspath(manifest)) or ".", "monitor_log.jsonl")

def _last(logp):
    last = "0" * 64
    if os.path.exists(logp):
        with open(logp, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    last = json.loads(line)["chain"]
                except (json.JSONDecodeError, KeyError, ValueError):
                    raise corpus.CorpusError("E_LOG_CORRUPT")
    return last

def _record(manifest, kind, fact):
    logp = _logp(manifest)
    try:
        prev = _last(logp)
    except corpus.CorpusError as e:
        sys.stderr.write("monitor: not extending a corrupt log (" + e.reason + ")\n")
        return
    e = {"kind": kind, "fact": fact, "prev": prev}
    e["chain"] = sha((prev + kind + json.dumps(fact, sort_keys=True)).encode())
    with open(logp, "a", encoding="utf-8") as f:
        f.write(json.dumps(e, sort_keys=True) + "\n")

def report(manifest):
    with open(manifest, encoding="utf-8") as f:
        db = json.load(f)
    try:
        version, csha, markers = corpus.load()
    except corpus.CorpusError as e:
        say("=== EXTERNAL ACCOUNTABILITY REPORT ===")
        say("baseline: " + manifest)
        say("corpus=" + governed(LATTICE, "UNVERIFIABLE") + " reason=" + e.reason)
        _record(manifest, "report", {"result": "UNVERIFIABLE", "reason": e.reason})
        emit("report", governed(LATTICE, "UNVERIFIABLE"), 2, subject=manifest, reason=e.reason)
    drift = missing = total = 0; results = []
    say("=== EXTERNAL ACCOUNTABILITY REPORT ===")
    say("baseline: " + manifest)
    say("corpus_version=" + str(version) + " corpus_sha256=" + csha)
    for p in sorted(db):
        want = db[p]
        if not os.path.isfile(p):
            say(governed(MONITOR_FILE, "MISSING") + "  markers=  -  " + os.path.basename(p)); missing += 1
            results.append({"file": os.path.basename(p), "status": "MISSING"}); continue
        try:
            with open(p, "rb") as fh:
                b = fh.read()
        except OSError:
            say(governed(MONITOR_FILE, "MISSING") + "  markers=  -  " + os.path.basename(p) + " reason=E_NO_RAW_CHANNEL"); missing += 1
            results.append({"file": os.path.basename(p), "status": "MISSING", "reason": "E_NO_RAW_CHANNEL"}); continue
        got = sha(b); hits = corpus.count(b, markers); total += hits
        st = governed(MONITOR_FILE, "MATCH" if got == want else "DRIFT")
        if got != want: drift += 1
        say(st + "  markers=" + str(hits).rjust(3) + "  " + os.path.basename(p))
        results.append({"file": os.path.basename(p), "status": st, "markers": hits})
    verdict = governed(MONITOR_BASELINE, "INTACT" if drift == 0 and missing == 0 else "CHANGED")
    say("files=" + str(len(db)) + " drift=" + str(drift) + " missing=" + str(missing) + " markers=" + str(total) + " baseline=" + verdict)
    _record(manifest, "report", {"files": len(db), "drift": drift, "missing": missing, "markers": total, "verdict": verdict, "corpus_version": version})
    # baseline CHANGED (drift and/or missing) is a NEGATIVE FINDING -> exit 1
    # (SPEC s.5); INTACT -> 0. A corpus that cannot load is UNVERIFIABLE -> 2 (above).
    emit("report", verdict, 0 if verdict == "INTACT" else 1, subject=manifest,
         corpus_version=version, corpus_sha256=csha, files=len(db), drift=drift,
         missing=missing, markers=total, results=results)

def reanchor(manifest):
    with open(manifest, encoding="utf-8") as f:
        db = json.load(f)
    changed = 0; new = {}
    for p in sorted(db):
        if not os.path.isfile(p):
            say("skip MISSING " + p); continue
        try:
            with open(p, "rb") as fh:
                h = sha(fh.read())
        except OSError:
            say("skip UNREADABLE " + p + " reason=E_NO_RAW_CHANNEL"); continue
        if h != db[p]: changed += 1
        new[p] = h
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump(new, f, indent=2, sort_keys=True)
    say("reanchored=" + str(len(new)) + " updated=" + str(changed) + " (operator authorized current state as baseline)")
    _record(manifest, "reanchor", {"reanchored": len(new), "updated": changed})
    emit("reanchor", None, 0, subject=manifest, reanchored=len(new), updated=changed)

def main():
    a = [x for x in sys.argv if x != "--json"]
    if len(a) != len(sys.argv):
        enable_json()
    if   len(a) >= 3 and a[1] == "report":   report(a[2])
    elif len(a) >= 3 and a[1] == "reanchor": reanchor(a[2])
    else: print(__doc__); sys.exit(64)

if __name__ == "__main__":
    main()
