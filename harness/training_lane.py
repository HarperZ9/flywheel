"""training_lane.py -- READ-ONLY status of the 32B QLoRA supervisor (SUPERAPP.md
subsystem b, the status half). Watches; it does not touch the safety envelope.

The supervisor (`scripts/run_phase2_32b_supervised.sh`) is the authority. This
module reads three sources and reconciles them into one honest status doc:

  supervisor log   logs/phase2-32b-supervisor.log -- regex-stable lines the
                   supervisor already emits ("RAM gate waiting/open", "attempt
                   N/12", "training completed with rc=0", "gave up after ...").
  screen liveness  `wsl screen -ls` for the `train32b` session -- the SOLE
                   liveness claim, so the status can never DISAGREE with screen
                   about whether the run is alive (that disagreement is the
                   subsystem's falsifier). The log-derived `state` is a separate
                   descriptor; `reconciled` flags when the two diverge.
  checkpoints      checkpoints/phase2-linux-qlora-cpt-32b/checkpoint-<step> --
                   latest optimizer step vs the ~2,019-step recipe-parity target.

It builds NO controls here: no start, no stop, no RAM-gate knob. The gated
start/graceful-stop actions are a separate, operator-confirmed surface. What this
module DOES expose for that surface is the pure `would_double_launch` guard, so a
start is refused when a `train32b` screen is already alive or the lock file exists.

Path contract (treat as API): everything large lives on E:. The E:\\ <-> /mnt/e
translator bridges the Windows status reader and the WSL supervisor.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import PurePosixPath, PureWindowsPath

SCHEMA = "flywheel.training-status/v1"
RUN_ROOT = "E:/local-model-run"
SUP_LOG_REL = "logs/phase2-32b-supervisor.log"
CKPT_REL = "checkpoints/phase2-linux-qlora-cpt-32b"
STOP_REL = "STOP_32B"
LOCK_REL = "train32b.lock"
SCREEN_NAME = "train32b"
TARGET_STEPS = 2019          # --epochs 0.25 at this packing lands ~2,019 steps
MAX_ATTEMPTS = 12

STATES = ("stopped", "waiting-for-RAM", "training", "completed", "gave-up", "unknown")

# Ordered (regex, state) -- applied line by line, LAST match wins. The markers are
# copied verbatim from run_phase2_32b_supervised.sh; if the supervisor changes a
# line, tests that assert against real log fixtures must fail, not this silently.
_MARKERS = [
    (re.compile(r"supervisor start:"), "training"),        # up and proceeding to the gate
    (re.compile(r"RAM gate waiting:"), "waiting-for-RAM"),
    (re.compile(r"RAM gate open:"), "training"),           # about to launch an attempt
    (re.compile(r"attempt \d+/\d+ \(resume_flag"), "training"),
    (re.compile(r"stop file (present|appeared)"), "stopped"),
    (re.compile(r"RAM gate timeout"), "gave-up"),
    (re.compile(r"aborting: RAM never freed"), "gave-up"),
    (re.compile(r"gave up after \d+ attempts"), "gave-up"),
    (re.compile(r"training completed with rc=0"), "completed"),
]
_ATTEMPT_RE = re.compile(r"attempt (\d+)/(\d+)")


def to_wsl(win_path: str) -> str:
    """E:\\local-model-run -> /mnt/e/local-model-run (drive letter lowercased)."""
    p = PureWindowsPath(win_path)
    drive = p.drive.rstrip(":").lower()
    rest = "/".join(p.parts[1:]) if p.drive else "/".join(p.parts)
    return f"/mnt/{drive}/{rest}" if drive else "/" + rest


def to_win(wsl_path: str) -> str:
    """/mnt/e/local-model-run -> E:\\local-model-run."""
    parts = PurePosixPath(wsl_path).parts
    if len(parts) >= 3 and parts[1] == "mnt":
        drive = parts[2].upper()
        rest = PureWindowsPath(*parts[3:]) if len(parts) > 3 else PureWindowsPath()
        return str(PureWindowsPath(f"{drive}:\\") / rest)
    return str(PureWindowsPath(wsl_path))


def parse_supervisor_log(text: str) -> dict:
    """Derive (state, last_event, attempt, max_attempts) from the supervisor log.
    Last recognized marker wins; unrecognized-but-present log -> 'unknown'."""
    state = "unknown"
    last_event = ""
    attempt = None
    max_attempts = MAX_ATTEMPTS
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        for rx, st in _MARKERS:
            if rx.search(line):
                state = st
                last_event = line
                break
        m = _ATTEMPT_RE.search(line)
        if m:
            attempt = int(m.group(1))
            max_attempts = int(m.group(2))
    return {"state": state, "last_event": last_event,
            "attempt": attempt, "max_attempts": max_attempts}


def latest_checkpoint_step(ckpt_dir) -> int | None:
    """Highest checkpoint-<N> step under the checkpoint dir, or None. The dir name
    IS the optimizer step (checkpoint-2020 == step 2020); robust without a JSON
    parse, falling back to trainer_state.json global_step if only that is present."""
    from pathlib import Path
    d = Path(ckpt_dir)
    if not d.is_dir():
        return None
    steps = []
    for child in d.glob("checkpoint-*"):
        m = re.fullmatch(r"checkpoint-(\d+)", child.name)
        if m:
            steps.append(int(m.group(1)))
    if steps:
        return max(steps)
    ts = d / "trainer_state.json"
    if ts.is_file():
        try:
            import json
            return int(json.loads(ts.read_text(encoding="utf-8")).get("global_step"))
        except Exception:
            return None
    return None


def screen_alive(name: str = SCREEN_NAME, *, timeout: float = 5.0) -> bool | None:
    """Probe `wsl screen -ls` for a live session. Returns True/False, or None when
    the probe itself could not run (honest 'unprobed' -- never a false 'dead')."""
    try:
        out = subprocess.run(["wsl", "screen", "-ls"], capture_output=True,
                             text=True, timeout=timeout)
    except Exception:
        return None
    return _screen_alive_from_blob((out.stdout or "") + (out.stderr or ""), name)


def _screen_alive_from_blob(blob: str, name: str = SCREEN_NAME) -> bool:
    """Pure `screen -ls` parser (testable without wsl). A session line is
    `<pid>.<name>\\t(Attached|Detached|Dead ???)`. `screen -ls` keeps a crashed
    session listed as `(Dead ???)` until `screen -wipe`, so a bare token match would
    report a dead socket as ALIVE -- the SOLE liveness source must not do that. A
    line is live only if it matches the name AND is not Dead-marked."""
    sess = re.compile(rf"\b\d+\.{re.escape(name)}\b")
    for line in blob.splitlines():
        if sess.search(line) and "(Dead" not in line:
            return True
    return False


def would_double_launch(*, screen_is_alive: bool | None, lock_present: bool) -> bool:
    """The start guard (pure): refuse a launch when a train32b screen is already
    alive OR the lock file exists. A None (unprobed) liveness is treated as a
    possible-live REFUSAL -- fail safe, never spawn a second contending supervisor."""
    return bool(lock_present) or screen_is_alive is not False


def _reconcile(state: str, alive: bool | None) -> tuple[bool | None, str]:
    """Does the log-derived state agree with screen liveness? None if unprobed."""
    if alive is None:
        return None, "liveness unprobed (wsl screen -ls did not run)"
    if state in ("training", "waiting-for-RAM") and not alive:
        return False, ("log's last event is an in-flight live-process state but no "
                       "train32b screen is alive -- the supervisor died without a "
                       "terminal line (it was mid-attempt or mid RAM-gate wait)")
    if state in ("completed", "stopped", "gave-up") and alive:
        return False, (f"log shows terminal state '{state}' but a train32b screen "
                       f"is still alive -- stale screen, inspect it")
    return True, "log state and screen liveness agree"


def training_status(run_root: str = RUN_ROOT, *, screen_probe=None) -> dict:
    """Compose the read-only status doc. screen_probe is injectable so the liveness
    source can be faked in tests; resolved at CALL time (default `screen_alive`,
    which shells `wsl screen -ls`) so a monkeypatched probe is honored."""
    from pathlib import Path
    probe = screen_probe or screen_alive
    root = Path(run_root)
    log_p = root / SUP_LOG_REL
    if log_p.is_file():
        parsed = parse_supervisor_log(log_p.read_text(encoding="utf-8", errors="replace"))
        log_present = True
    else:
        parsed = {"state": "stopped", "last_event": "", "attempt": None,
                  "max_attempts": MAX_ATTEMPTS}
        log_present = False
    step = latest_checkpoint_step(root / CKPT_REL)
    alive = probe()
    reconciled, note = _reconcile(parsed["state"], alive)
    return {
        "schema": SCHEMA,
        "state": parsed["state"],
        "screen_alive": alive,                 # the SOLE liveness claim (from screen)
        "log_present": log_present,
        "last_event": parsed["last_event"],
        "attempt": parsed["attempt"],
        "max_attempts": parsed["max_attempts"],
        "checkpoint_step": step,
        "target_steps": TARGET_STEPS,
        "progress": round(step / TARGET_STEPS, 4) if step is not None else None,
        "stop_flag_present": (root / STOP_REL).exists(),
        "lock_present": (root / LOCK_REL).exists(),
        "reconciled": reconciled,
        "note": note,
        "run_root": str(run_root),
    }


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(training_status(sys.argv[1] if len(sys.argv) > 1 else RUN_ROOT),
                     indent=1))
