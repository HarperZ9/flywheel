#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""
membrane.py - Coherence Membrane: an externally-anchored integrity layer.

Its integrity comes ENTIRELY from re-derivability, never from authority.
It refuses every in-band authority claim - including any claim to trust
itself. Every line it prints is reproducible by re-running this code on the
same raw bytes. No secret state, no "trust me", no safety adjudication.

Held by construction:
  externally anchored - reads raw bytes via open('rb'); never a mediated view
  hash-pinned         - facts are sha256 over SOURCE bytes; a view is checked
                        AGAINST source, never substituted for it
  authority-refusing  - in-band authority/scope claims are detected, stripped,
                        and logged; never obeyed (its own included)
  tamper-evident      - attestations chain by hash; retroactive edits show
  facts-only          - emits hashes/sizes/verdicts; never permission/identity
  advisory            - verdict is in stdout + exit code; the OPERATOR decides

Honest limits (a membrane that calls itself bulletproof has already lied):
  * its own correctness is checked OUT-OF-BAND: this file's sha256 is its
    identity; re-derive it from source and you get the same hash. That
    reproducibility - not this docstring - is the only assurance offered.
  * the authority-marker set is a denylist of KNOWN signatures, not a proof
    of completeness; absence of a flag is not a guarantee of cleanliness.
  * with no raw-byte channel it reports UNVERIFIABLE - never TRUSTED.

Usage:
  membrane.py anchor      <path>...              -> pin raw-byte hashes
  membrane.py verify      <path>...              -> MATCH/DRIFT vs anchors
  membrane.py coherence   <source> <view_file>   -> source-vs-view hash compare
  membrane.py refuse      <file>                 -> detect+strip in-band authority
  membrane.py corroborate <path>                 -> read-path-diverse agreement
  membrane.py audit                              -> verify the tamper-evident log
  membrane.py selftest                           -> re-derive my own identity
  membrane.py receipt --from-json <file|->       -> emit a portable witness receipt
  membrane.py check <receipt.json>               -> offline re-verify a receipt
  membrane.py rebind <naked> --manifest <m.json> -> rebind stripped bytes (EXPERIMENTAL)
"""
import sys, os, json, hashlib, subprocess
from . import corpus
from . import report
from . import witness_receipt
from . import rebind as rebind_mod
from .report import say, emit
from .verdict import governed, LATTICE, COHERENCE, CORROBORATE, AUDIT, RECEIPT

ANCHORS, LOG = "anchors.json", "membrane_log.jsonl"

# Exit codes (SPEC s.5, NORMATIVE at 1.0): 0 held; 1 negative finding (DRIFT /
# VIEW_DIFFERS / QUARANTINE / BROKEN); 2 UNVERIFIABLE; 3 markers; 64 usage. A
# non-zero exit is data, never an authority decision (Boundary 4).
EXIT_OK, EXIT_DIFF, EXIT_UNVERIFIABLE, EXIT_MARKERS, EXIT_USAGE = 0, 1, 2, 3, 64

def raw(path):
    with open(path, "rb") as f:
        return f.read()

def try_raw(path):
    # SPEC sections 3 and 9: with no raw byte channel, report UNVERIFIABLE with a
    # STABLE MACHINE REASON CODE - never crash, never substitute a default.
    # Returns (bytes, None) on success or (None, reason_code) on inability.
    try:
        with open(path, "rb") as f:
            return f.read(), None
    except FileNotFoundError:
        return None, "E_NOT_FOUND"
    except (PermissionError, IsADirectoryError, OSError):
        return None, "E_NO_RAW_CHANNEL"

def sha(b):
    return hashlib.sha256(b).hexdigest()

def _load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _last_chain():
    last = "0" * 64
    if os.path.exists(LOG):
        with open(LOG, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    last = json.loads(line)["chain"]
                except (json.JSONDecodeError, KeyError, ValueError):
                    # A corrupt log line is a tamper event, not a crash. Refuse to
                    # chain off corruption; record() handles this controlled error.
                    raise corpus.CorpusError("E_LOG_CORRUPT")
    return last

def record(kind, fact):
    # Best-effort tamper-evident logging. If the log is already corrupt, refuse to
    # extend it (chaining off a break would hide it); audit surfaces the break.
    try:
        prev = _last_chain()
    except corpus.CorpusError as e:
        sys.stderr.write("membrane: not extending a corrupt log (" + e.reason + ")\n")
        return
    e = {"kind": kind, "fact": fact, "prev": prev}
    e["chain"] = sha((prev + kind + json.dumps(fact, sort_keys=True)).encode())
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(e, sort_keys=True) + "\n")

def _key(p):
    # Anchor-store key: forward slashes so anchors.json is portable across OS.
    return os.path.normpath(p).replace(os.sep, "/")

# Artifact-of-record (SPEC s.14): the core source file set (hashed sorted-by-name).
CORE_SRC = ("corpus.py", "membrane.py", "monitor.py", "organs.py", "report.py", "verdict.py")

def anchor(paths):
    db = _load_json(ANCHORS)
    bad = 0; results = []
    for p in paths:
        p = _key(p); b, err = try_raw(p)
        if err:
            say(governed(LATTICE, "UNVERIFIABLE") + " " + p + " reason=" + err)
            results.append({"path": p, "verdict": "UNVERIFIABLE", "reason": err}); bad += 1; continue
        h = sha(b); db[p] = h
        say("anchored " + p + " sha256=" + h); record("anchor", {"path": p, "sha256": h})
        results.append({"path": p, "sha256": h})
    with open(ANCHORS, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, sort_keys=True)
    # anchor only ever produces UNVERIFIABLE (an unreadable path) or clean; it
    # never drifts. An unreadable target is UNVERIFIABLE, never a silent skip.
    emit("anchor", None, EXIT_UNVERIFIABLE if bad else EXIT_OK, results=results)

def verify(paths):
    db = _load_json(ANCHORS)
    drift = unver = 0; results = []
    for p in paths:
        p = _key(p); want = db.get(p)
        if want is None:
            say(governed(LATTICE, "UNVERIFIABLE") + " " + p + " reason=E_NO_ANCHOR")
            results.append({"path": p, "verdict": "UNVERIFIABLE", "reason": "E_NO_ANCHOR"}); unver += 1; continue
        b, err = try_raw(p)
        if err:
            say(governed(LATTICE, "UNVERIFIABLE") + " " + p + " reason=" + err)
            record("verify", {"path": p, "result": "UNVERIFIABLE", "reason": err})
            results.append({"path": p, "verdict": "UNVERIFIABLE", "reason": err}); unver += 1; continue
        got = sha(b); ok = got == want; v = "MATCH" if ok else "DRIFT"
        say(governed(LATTICE, v) + " " + p + " want=" + want[:16] + " got=" + got[:16])
        record("verify", {"path": p, "result": v})
        results.append({"path": p, "verdict": v, "want": want, "got": got})
        if not ok:
            drift += 1
    # Precedence (SPEC s.5): a confirmed difference dominates an inability to
    # check. Exit 1 if any path DRIFTed, else 2 if any was UNVERIFIABLE, else 0.
    dom = "DRIFT" if drift else ("UNVERIFIABLE" if unver else "MATCH")
    emit("verify", governed(LATTICE, dom),
         EXIT_DIFF if drift else (EXIT_UNVERIFIABLE if unver else EXIT_OK), results=results)

def coherence(source, view_file):
    sb, serr = try_raw(source); vb, verr = try_raw(view_file)
    if serr or verr:
        why = ("source:" + serr) if serr else ("view:" + verr)
        say("result=" + governed(COHERENCE, "UNVERIFIABLE") + " reason=" + why)
        record("coherence", {"source": _key(source), "result": "UNVERIFIABLE", "reason": why})
        emit("coherence", governed(COHERENCE, "UNVERIFIABLE"), EXIT_UNVERIFIABLE,
             subject=_key(source), reason=why)
    s, v = sha(sb), sha(vb)
    ok = s == v; res = "COHERENT" if ok else "VIEW_DIFFERS_FROM_SOURCE"
    say("source=" + s); say("view  =" + v)
    say("result=" + governed(COHERENCE, res))
    record("coherence", {"source": _key(source), "result": res})
    emit("coherence", governed(COHERENCE, res), EXIT_OK if ok else EXIT_DIFF,
         subject=_key(source), source=s, view=v)

def refuse(path):
    b, err = try_raw(path)
    if err:
        say(governed(LATTICE, "UNVERIFIABLE") + " " + path + " reason=" + err)
        record("refuse", {"path": _key(path), "result": "UNVERIFIABLE", "reason": err})
        emit("refuse", governed(LATTICE, "UNVERIFIABLE"), EXIT_UNVERIFIABLE, subject=_key(path), reason=err)
    try:
        version, csha, markers = corpus.load()
    except corpus.CorpusError as e:
        say(governed(LATTICE, "UNVERIFIABLE") + " " + path + " reason=" + e.reason)
        record("refuse", {"path": _key(path), "result": "UNVERIFIABLE", "reason": e.reason})
        emit("refuse", governed(LATTICE, "UNVERIFIABLE"), EXIT_UNVERIFIABLE, subject=_key(path), reason=e.reason)
    hits, clean = corpus.scan(b, markers)
    with open(path + ".refused", "wb") as f:
        f.write(clean)
    say("corpus_version=" + str(version))
    say("corpus_sha256=" + csha)
    say("in_band_authority_claims=" + str(len(hits)))
    for off, ln in hits[:60]:
        say("  REFUSED " + repr(b[off:off + ln].decode("latin-1")) + " offset=" + str(off))
    say("clean_copy=" + path + ".refused  (claims neutralized; obeyed: none)")
    record("refuse", {"path": _key(path), "refused": len(hits), "corpus_version": version})
    emit("refuse", None, EXIT_OK if not hits else EXIT_MARKERS, subject=_key(path),
         in_band_authority_claims=len(hits), corpus_version=version, corpus_sha256=csha,
         hits=[{"marker": b[o:o + ln].decode("latin-1"), "offset": o} for o, ln in hits],
         clean_copy=path + ".refused")

def corroborate(path):
    # read-path diversity: hash the SAME file via disjoint channels; agreement
    # across channels is the signal. catches a tampered READ PATH, not just a
    # broken hash tool.
    a, err = try_raw(path)
    if err:
        say("open_rb=unavailable:" + err)
        say("read_paths_agree=False")
        say("result=" + governed(CORROBORATE, "UNVERIFIABLE") + " reason=" + err)
        record("corroborate", {"path": _key(path), "result": "UNVERIFIABLE", "reason": err})
        emit("corroborate", governed(CORROBORATE, "UNVERIFIABLE"), EXIT_UNVERIFIABLE, subject=_key(path), reason=err)
    paths = {"open_rb": sha(a)}
    try:
        o = subprocess.run(["cat", path], capture_output=True, timeout=20)
        paths["cat_subproc"] = sha(o.stdout)
    except Exception as e:
        paths["cat_subproc"] = "unavailable:" + type(e).__name__
    def git_blob(b):
        return hashlib.sha1(b"blob " + str(len(b)).encode() + b"\x00" + b).hexdigest()
    try:
        o = subprocess.run(["git", "hash-object", "--no-filters", path], capture_output=True, text=True, timeout=20)
        git_reported = (o.stdout.split() or [""])[0]
        paths["git_read"] = git_reported
        git_agrees = bool(git_reported) and git_reported == git_blob(a)
    except Exception as e:
        paths["git_read"] = "unavailable:" + type(e).__name__
        git_agrees = None
    sha_vals = {v for k, v in paths.items() if k in ("open_rb", "cat_subproc") and ":" not in v}
    sha_agree = len(sha_vals) == 1
    for k, v in sorted(paths.items()): say(k + "=" + v)
    say("read_paths_agree=" + str(sha_agree))
    say("git_read_agrees_with_open=" + str(git_agrees))
    cat_ok = ":" not in paths.get("cat_subproc", ":")
    git_ok = git_agrees is not None
    if not (cat_ok or git_ok):
        # only open_rb succeeded: no independent read path, so there is no
        # divergence signal to corroborate. Inability, not agreement (SPEC 9).
        say("result=" + governed(CORROBORATE, "UNVERIFIABLE") + " reason=E_NO_SECOND_READ_PATH")
        record("corroborate", {"path": _key(path), "result": "UNVERIFIABLE", "reason": "E_NO_SECOND_READ_PATH"})
        emit("corroborate", governed(CORROBORATE, "UNVERIFIABLE"), EXIT_UNVERIFIABLE,
             subject=_key(path), reason="E_NO_SECOND_READ_PATH", channels=paths)
    ok = sha_agree and (git_agrees in (True, None))
    res = "CORROBORATED" if ok else "QUARANTINE_READ_PATH_DIVERGENCE"
    say("result=" + governed(CORROBORATE, res))
    record("corroborate", {"path": _key(path), "agree": sha_agree, "git": git_agrees})
    emit("corroborate", governed(CORROBORATE, res), EXIT_OK if ok else EXIT_DIFF,
         subject=_key(path), channels=paths, read_paths_agree=sha_agree, git_read_agrees_with_open=git_agrees)

def audit():
    if not os.path.exists(LOG):
        # An absent log is the genesis state: an empty chain is trivially intact.
        # Emit the chain= line (SPEC s.13) rather than a special-case string.
        say("log_entries=0 chain=" + governed(AUDIT, "INTACT"))
        emit("audit", governed(AUDIT, "INTACT"), EXIT_OK, log_entries=0)
    prev, ok, n = "0" * 64, True, 0
    broken_at = broken_reason = None
    with open(LOG, encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            n += 1
            try:
                e = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                # A corrupt line IS a tamper event — report BROKEN, never crash.
                say(governed(AUDIT, "BROKEN") + " at entry " + str(n) + " (parse error)")
                ok = False; broken_at = n; broken_reason = "parse_error"; break
            if not all(k in e for k in ("kind", "fact", "prev", "chain")) \
               or e["prev"] != prev \
               or e["chain"] != sha((e["prev"] + e["kind"] + json.dumps(e["fact"], sort_keys=True)).encode()):
                say(governed(AUDIT, "BROKEN") + " at entry " + str(n)); ok = False; broken_at = n; break
            prev = e["chain"]
    v = "INTACT" if ok else "BROKEN"
    say("log_entries=" + str(n) + " chain=" + governed(AUDIT, v))
    emit("audit", governed(AUDIT, v), EXIT_OK if ok else EXIT_DIFF,
         log_entries=n, broken_at=broken_at, broken_reason=broken_reason)

def selftest():
    # SPEC s.14: canonical token emet_self_sha256=; the legacy
    # membrane_self_sha256= is emitted through the 1.x window (removed at 2.0).
    h = report.self_hash(os.path.dirname(os.path.abspath(__file__)), CORE_SRC)
    say("emet_self_sha256=" + h)
    say("membrane_self_sha256=" + h + "  (deprecated alias; removed at 2.0)")
    say("note=re-derive this hash from the source files to check this build.")
    say("note=emet reports hashes and verdicts; it grants no permission.")
    emit("selftest", None, EXIT_OK, self_sha256=h,
         notes=["re-derive this hash from the source files to check this build.",
                "emet reports hashes and verdicts; it grants no permission."])

RECEIPT_USAGE = (
    "usage: emet receipt --from-json <file|->   emit a portable witness receipt\n"
    "       emet check <receipt.json> [--recompute-from-paths]   offline re-verify\n"
    "\n"
    "receipt reads a command envelope (verify/anchor/coherence/corroborate --json)\n"
    "from a file or stdin (-) and prints a self-contained, content-addressed\n"
    "witness receipt (SPEC s.17) to stdout. Anyone can check it on their own\n"
    "machine with `emet check`; no shared state is needed.\n"
)

def _receipt_signing_key():
    # Optional HMAC key from the env (out-of-spec, SPEC s.17). Absent -> None ->
    # content-addressing alone. Never logged, never echoed.
    k = os.environ.get(witness_receipt.SIGNING_KEY_ENV)
    return k.encode("utf-8") if k else None

def receipt_cmd(args):
    # args are the tokens AFTER "receipt". Only --from-json <file|-> is supported.
    if len(args) >= 2 and args[0] == "--from-json":
        src = args[1]
        try:
            raw_json = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
            env = json.loads(raw_json)
        except (OSError, ValueError, UnicodeDecodeError) as e:
            sys.stderr.write("emet receipt: cannot read --from-json source (" + type(e).__name__ + ")\n")
            sys.exit(EXIT_USAGE)
        # issued_at is the one wall-clock field; pin it here so the receipt is
        # self-describing. Tests inject a fixed value via the library seam or the
        # EMET_RECEIPT_NOW env seam (mirrored by the Rust/Node ports) so a
        # cross-implementation receipt_id parity check is deterministic.
        import datetime
        now = os.environ.get("EMET_RECEIPT_NOW") or \
            datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = witness_receipt.emit_receipt(env, base_dir=os.getcwd(), now=now,
                                         signing_key=_receipt_signing_key())
        print(report.canonical(r))
        sys.exit(EXIT_OK)
    sys.stderr.write(RECEIPT_USAGE)
    sys.exit(EXIT_USAGE)

def check_cmd(args):
    # emet check <receipt.json> [--recompute-from-paths]. Stateless offline
    # re-verification: RECEIPT_VALID (0) / RECEIPT_TAMPERED (1) / RECEIPT_UNVERIFIABLE (2).
    recompute = "--recompute-from-paths" in args
    positional = [x for x in args if not x.startswith("-")]
    if not positional:
        sys.stderr.write(RECEIPT_USAGE)
        sys.exit(EXIT_USAGE)
    path = positional[0]
    try:
        r = witness_receipt.load_receipt(path)
    except ValueError as e:
        say(governed(RECEIPT, "RECEIPT_UNVERIFIABLE") + " " + path + " reason=" + str(e))
        emit("check", governed(RECEIPT, "RECEIPT_UNVERIFIABLE"), EXIT_UNVERIFIABLE,
             subject=path, reason=str(e))
        return
    # Subjects are recorded relative to the receipt's producer cwd; re-derive them
    # relative to the receipt file's directory so a portable receipt+subject pair
    # checks in place.
    base = os.path.dirname(os.path.abspath(path)) or "."
    verdict, detail = witness_receipt.check_receipt(
        r, base_dir=base, recompute=recompute, signing_key=_receipt_signing_key())
    say("result=" + verdict + " reason=" + detail)
    code = {"RECEIPT_VALID": EXIT_OK, "RECEIPT_TAMPERED": EXIT_DIFF,
            "RECEIPT_UNVERIFIABLE": EXIT_UNVERIFIABLE}[verdict]
    emit("check", verdict, code, subject=path, detail=detail,
         receipt_id=r.get("receipt_id"))

REBIND_USAGE = (
    "usage: emet rebind <naked-bytes> --manifest <manifest.json> [--claim <identity>]\n"
    "       emet rebind --build-manifest <path>=<identity> [<path>=<identity> ...]\n"
    "\n"
    "rebind re-derives the content hash of stripped naked bytes and rebinds them to\n"
    "a KNOWN anchor recorded in a portable rebind manifest (SPEC s.18, EXPERIMENTAL),\n"
    "emitting MATCH / DRIFT / UNVERIFIABLE. UNVERIFIABLE means no anchor records\n"
    "the bytes. --build-manifest constructs a manifest from\n"
    "path=identity pairs (each path's raw bytes are hashed into an anchor record).\n"
)


def build_manifest_cmd(pairs):
    # emet rebind --build-manifest <path>=<identity> ... -> print a content-addressed
    # rebind manifest to stdout. Each pair anchors a path's raw-byte digest to an
    # identity; an unreadable path is UNVERIFIABLE + exit 2, never a silent skip.
    records = []
    for pair in pairs:
        if "=" not in pair:
            sys.stderr.write("emet rebind --build-manifest: expected <path>=<identity>, got " + repr(pair) + "\n")
            sys.exit(EXIT_USAGE)
        path, identity = pair.split("=", 1)
        b, err = try_raw(path)
        if err:
            say(governed(LATTICE, "UNVERIFIABLE") + " " + path + " reason=" + err)
            emit("rebind-build-manifest", governed(LATTICE, "UNVERIFIABLE"),
                 EXIT_UNVERIFIABLE, subject=_key(path), reason=err)
            return
        records.append({"digest": sha(b), "identity": identity})
    now = os.environ.get("EMET_REBIND_NOW")
    if now is None:
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        manifest = rebind_mod.build_manifest(records, issued_at=now)
    except ValueError as e:
        sys.stderr.write("emet rebind --build-manifest: " + str(e) + "\n")
        sys.exit(EXIT_USAGE)
    print(report.canonical(manifest))
    sys.exit(EXIT_OK)


def rebind_cmd(args):
    # emet rebind <naked> --manifest <m.json> [--claim <id>]
    #   | emet rebind --build-manifest <path>=<identity> ...
    if args and args[0] == "--build-manifest":
        pairs = args[1:]
        if not pairs:
            sys.stderr.write(REBIND_USAGE)
            sys.exit(EXIT_USAGE)
        build_manifest_cmd(pairs)
        return
    naked = manifest_path = claim = None
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--manifest" and i + 1 < len(args):
            manifest_path = args[i + 1]; i += 2; continue
        if tok == "--claim" and i + 1 < len(args):
            claim = args[i + 1]; i += 2; continue
        if not tok.startswith("-") and naked is None:
            naked = tok; i += 1; continue
        i += 1
    if naked is None or manifest_path is None:
        sys.stderr.write(REBIND_USAGE)
        sys.exit(EXIT_USAGE)
    # The naked bytes: read raw, never a mediated view. Unreadable -> UNVERIFIABLE.
    b, err = try_raw(naked)
    if err:
        say("result=" + governed(LATTICE, "UNVERIFIABLE") + " reason=" + err)
        record("rebind", {"naked": _key(naked), "result": "UNVERIFIABLE", "reason": err})
        emit("rebind", governed(LATTICE, "UNVERIFIABLE"), EXIT_UNVERIFIABLE,
             subject=_key(naked), reason=err, experimental=True)
        return
    try:
        manifest = rebind_mod.load_manifest(manifest_path)
    except ValueError as e:
        say("result=" + governed(LATTICE, "UNVERIFIABLE") + " reason=" + str(e))
        record("rebind", {"naked": _key(naked), "result": "UNVERIFIABLE", "reason": "E_MANIFEST_UNREADABLE"})
        emit("rebind", governed(LATTICE, "UNVERIFIABLE"), EXIT_UNVERIFIABLE,
             subject=_key(naked), reason=str(e), experimental=True)
        return
    verdict, detail, digest = rebind_mod.rebind_manifest(b, manifest, claim=claim)
    say("naked=" + _key(naked))
    say("derived_digest=" + digest)
    if claim is not None:
        say("claim=" + claim)
    say("manifest_id=" + str(manifest.get("manifest_id"))[:16])
    say("result=" + verdict + " reason=" + detail)
    record("rebind", {"naked": _key(naked), "digest": digest, "result": verdict,
                      "claim": claim, "manifest_id": manifest.get("manifest_id")})
    code = EXIT_OK if verdict == "MATCH" else (EXIT_DIFF if verdict == "DRIFT" else EXIT_UNVERIFIABLE)
    emit("rebind", verdict, code, subject=_key(naked), derived_digest=digest,
         claim=claim, detail=detail, manifest_id=manifest.get("manifest_id"),
         experimental=True)


def main():
    a = [x for x in sys.argv if x != "--json"]
    if len(a) != len(sys.argv):
        report.enable_json()
    if   len(a) >= 3 and a[1] == "anchor":      anchor(a[2:])
    elif len(a) >= 3 and a[1] == "verify":      verify(a[2:])
    elif len(a) >= 4 and a[1] == "coherence":   coherence(a[2], a[3])
    elif len(a) >= 3 and a[1] == "refuse":      refuse(a[2])
    elif len(a) >= 3 and a[1] == "corroborate": corroborate(a[2])
    elif len(a) >= 2 and a[1] == "audit":       audit()
    elif len(a) >= 2 and a[1] == "selftest":    selftest()
    elif len(a) >= 2 and a[1] == "receipt":     receipt_cmd(a[2:])
    elif len(a) >= 3 and a[1] == "check":       check_cmd(a[2:])
    elif len(a) >= 3 and a[1] == "rebind":      rebind_cmd(a[2:])
    else: print(__doc__); sys.exit(EXIT_USAGE)

if __name__ == "__main__":
    main()
