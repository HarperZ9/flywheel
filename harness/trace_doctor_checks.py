"""Doctor checks 3 to 12 (7.1). Each returns (state, detail, remedy).

States: PASS, WARN, FAIL, UNKNOWN. A check that cannot establish a fact says
UNKNOWN rather than guessing. No check prints a value read from a settings
file other than the hook entries and Claude Code's `cleanupPeriodDays`.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

DOCTOR = "flywheel traces doctor"


def token_check(home: Path):
    from harness.secret_file_label import has_lower_integrity_label
    path = home / "gateway.token"
    try:
        readable = bool(path.read_text(encoding="utf-8").strip())
    except OSError:
        return "FAIL", "no readable gateway token", "start the gateway once: flywheel gateway"
    if not readable:
        return "FAIL", "the gateway token is empty", "delete gateway.token and restart the gateway"
    label = has_lower_integrity_label(path)
    if label is False:
        return "WARN", "token readable; integrity label missing", "restart the gateway"
    note = "integrity label present" if label else "no integrity label on this system"
    return "PASS", f"token readable; {note}", ""


def channel_check(home: Path, environ, cwd: Path):
    from harness.capture_hooks.client import CaptureFailure, open_channel, read_token
    from harness.capture_hooks.home import resolve_home
    from harness.capture_hooks.listener_owner import method
    from harness.capture_hooks.protocol import PING_PATH
    _, refusal = resolve_home(str(home), {k: v for k, v in environ.items()
                                          if k != "FLYWHEEL_HOME"}, cwd)
    try:
        if refusal:
            raise CaptureFailure(refusal)
        open_channel(home, read_token(home), 5.0).request("GET", PING_PATH)
    except CaptureFailure as failure:
        return "FAIL", failure.code, "start the gateway, then run the doctor again"
    return "PASS", f"endpoint, listener ({method()}), proof and signed ping ok", ""


def settings_check(home: Path):
    from harness.trace_capture_settings import DEFAULTS, data_flow, effective
    from harness.trace_custody_ledger import read_owner_ref
    owner = read_owner_ref(home)
    current = effective(home, owner) if owner else {**DEFAULTS, "pending_change": False}
    detail = " ".join(data_flow(current))
    if current["pending_change"]:
        return ("WARN", detail + " A change on disk is not in effect.",
                "flywheel traces capture confirm")
    return "PASS", detail, ""


def failures_check(home: Path, ack: bool):
    from harness.capture_hooks import spool
    from harness.trace_capture_off import record_suppressions
    from harness.trace_custody_ledger import read_owner_ref
    if ack:
        spool.acknowledge(home)
    owner = read_owner_ref(home)
    if owner:
        record_suppressions(home, owner)
    reasons = Counter(r.get("reason_code", "UNKNOWN") for r in spool.failures(home))
    suppressed = _suppressed_by_project(spool.suppressions(home))
    detail = ", ".join(f"{code} x{n}" for code, n in sorted(reasons.items())) or "none"
    if suppressed:
        detail += "; suppressed: " + ", ".join(f"{k} x{n}" for k, n in suppressed)
    if reasons:
        return "WARN", f"unacknowledged failures: {detail}", f"{DOCTOR} --ack after fixing"
    return "PASS", f"no unacknowledged failures; {detail if suppressed else 'none suppressed'}", ""


def _suppressed_by_project(records) -> list[tuple[str, int]]:
    from harness.capture_hooks import protect
    import base64
    counts: Counter = Counter()
    for record in records:
        where = "total"
        blob = record.get("cwd_protected")
        if blob and protect.available():
            try:
                where = protect.unprotect(base64.b64decode(blob)).decode("utf-8")
            except (OSError, ValueError, UnicodeError):
                where = "unreadable"
        counts[where] += 1
    return sorted(counts.items())


def retention_check(environ, cwd: Path, now=None):
    from harness.trace_doctor_mounts import settings_files
    days, where = 30, "default"
    for label, path in settings_files(environ, cwd)[:3]:
        try:
            value = json.loads(path.read_bytes()).get("cleanupPeriodDays")
        except (OSError, ValueError, AttributeError):
            continue
        if type(value) is int and value >= 1:
            days, where = value, label
    at_risk = _near_sweep(environ, days, now or datetime.now(timezone.utc))
    detail = (f"cleanupPeriodDays {days} ({where}; managed settings not checked); "
              f"{at_risk} transcripts within 7 days of the sweep, none imported yet")
    remedy = ("set cleanupPeriodDays (3650 keeps about ten years) or import before the "
              "sweep; import lands with FW-10a") if at_risk else ""
    return ("WARN" if at_risk else "PASS"), detail, remedy


def _near_sweep(environ, days: int, now) -> int:
    from harness.capture_hooks.home import profile_dir
    root = Path(environ.get("CLAUDE_CONFIG_DIR") or (profile_dir() or Path.home()) / ".claude")
    cutoff = (now - timedelta(days=max(days - 7, 0))).timestamp()
    count = 0
    for path in (root / "projects").glob("*/*.jsonl") if (root / "projects").is_dir() else []:
        try:
            count += path.stat().st_mtime < cutoff
        except OSError:
            continue
    return count


def encryption_check(home: Path):
    from harness.trace_enc_probe import encryption_status
    status = encryption_status(home / "state")
    floored = ", ".join(sorted(status["floors"])) or "none yet"
    note = ("Encrypted data cannot be read on another machine or after a password reset. "
            "Export is the backup.")
    detail = f"{status['protection']}; floor set for {floored}. {note}"
    if status["provider"] == "none":
        return "WARN", detail, "on macOS or Linux install the encryption extra with a keychain"
    return "PASS", detail, ""


def presence_check(home: Path):
    from harness.trace_custody_ledger import CustodyLedger, read_owner_ref
    from harness.trace_presence import STATEMENT, presence_status
    from harness.trace_witness import default_sink, reconcile
    owner = read_owner_ref(home)
    status = presence_status(home / "state", owner) if owner else {
        "method": "none", "statement": STATEMENT}
    sink = default_sink()
    try:
        entries = CustodyLedger(home, owner).entries() if owner else []
        missing = reconcile(entries, sink.read(), owner)
        witness = f"{sink.status()}; {len(missing)} ledger entries without an event"
    except (OSError, ValueError) as exc:
        missing, witness = [], f"{sink.status()} unreadable ({type(exc).__name__})"
    detail = f"presence method {status['method']}: {status['statement']}; witness: {witness}"
    if missing:
        return "FAIL", detail + " (WITNESS_MISMATCH)", "compare the ledger with the event log"
    if status["method"] == "none" or sink.status().startswith("no witness"):
        return "WARN", detail, "flywheel traces presence set windows-hello"
    return "PASS", detail, ""


def disk_check(home: Path):
    return ("UNKNOWN", "BitLocker, shadow copy and File History state not established "
            "(shadow copies need administrator rights to list)",
            "check the volume's encryption and backups in Windows settings")


def location_check(home: Path, environ):
    from harness.capture_hooks.home import in_git_worktree
    text = os.path.normcase(os.path.abspath(str(home)))
    roots = [environ.get(k) for k in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")]
    synced = any(r and text.startswith(os.path.normcase(os.path.abspath(r))) for r in roots)
    synced = synced or any(w in text for w in ("dropbox", "google drive", "icloud"))
    if in_git_worktree(home):
        return "WARN", "the home is inside a git work tree", "move FLYWHEEL_HOME out of it"
    if synced:
        return "WARN", "the home is inside a sync folder", "move FLYWHEEL_HOME out of it"
    return "PASS", "the home is outside sync folders and git work trees", ""


def synthetic_check(home: Path, run: bool):
    if not run:
        return "UNKNOWN", "not run", f"{DOCTOR} --synthetic"
    session = f"flywheel-doctor-{secrets.token_hex(8)}"
    event = {"session_id": session, "hook_event_name": "Stop",
             "last_assistant_message": f"synthetic doctor turn {session}"}
    env = {k: v for k, v in os.environ.items() if not k.startswith("FLYWHEEL_")}
    package_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join(p for p in (package_root, env.get("PYTHONPATH")) if p)
    proc = subprocess.run([sys.executable, "-m", "harness.capture_hooks", "stop", "--client",
                           "claude-code", "--home", str(home)],
                          input=json.dumps(event).encode(), capture_output=True, env=env,
                          cwd=str(Path(sys.executable).parent), timeout=60)
    if proc.returncode != 0:
        return "FAIL", "the hook module could not record a synthetic turn", DOCTOR
    removed = _remove_synthetic(home, session)
    return ("PASS", "the Flywheel hook module recorded a synthetic turn; " + removed, "")


def _remove_synthetic(home: Path, session: str) -> str:
    """Delete what the doctor itself made, through the deletion engine, with
    presence method doctor-synthetic, which `confirm_synthetic` gives only to
    a plan it builds from this doctor session's own turns."""
    from harness.trace_custody_ledger import read_owner_ref
    from harness.trace_delete_apply import apply_plan
    from harness.trace_presence import PresenceError, confirm_synthetic
    owner = read_owner_ref(home)
    try:
        digest, ref = confirm_synthetic(home, owner, session) if owner else (None, None)
    except PresenceError:
        digest = None
    if digest is None:
        return "no synthetic record was found to remove"
    report = apply_plan(home, owner, digest, ref, reason="doctor_synthetic")
    return f"its records were removed ({report['state']})"
