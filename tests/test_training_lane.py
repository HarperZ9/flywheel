"""Falsifier for the training-lane read-only status (harness/training_lane.py).

Load-bearing properties:
  - the state machine maps the supervisor's REAL log markers to the right state.
  - liveness is the screen probe and ONLY the screen probe -- the status never
    claims a run is alive on its own; a log/screen divergence is flagged, not hidden.
  - the double-launch guard refuses a start when a screen is alive OR unprobed OR
    the lock exists (fail safe).
  - the E:\\ <-> /mnt/e translator round-trips.
This module builds no controls; there is nothing here that can lower a gate.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import training_lane as T


# --- log fixtures copied from run_phase2_32b_supervised.sh's emitted lines ------

def _ts(msg):
    return f"[2026-07-11T00:00:00Z] {msg}"


START = _ts("supervisor start: MODEL_SIZE=32B seq_len=256 epochs=0.25 max_attempts=12 ram_gate=22GB")
WAIT = _ts("RAM gate waiting: MemAvailable 12 GB < 22 GB; sleeping 120s")
OPEN = _ts("RAM gate open: MemAvailable 24 GB >= 22 GB")
ATTEMPT1 = _ts("attempt 1/12 (resume_flag='')")
ATTEMPT2 = _ts("attempt 2/12 (resume_flag='--resume')")
COMPLETED = _ts("training completed with rc=0 after attempt 2")
GAVEUP = _ts("gave up after 12 attempts; inspect /mnt/e/local-model-run/logs/phase2-linux-32b-full.log")
STOPPED = _ts("stop file present; exiting cleanly")
RAM_ABORT = _ts("aborting: RAM never freed")


def test_state_waiting_for_ram():
    p = T.parse_supervisor_log("\n".join([START, WAIT]))
    assert p["state"] == "waiting-for-RAM"


def test_state_training_on_attempt():
    p = T.parse_supervisor_log("\n".join([START, OPEN, ATTEMPT1]))
    assert p["state"] == "training"
    assert p["attempt"] == 1 and p["max_attempts"] == 12


def test_state_completed_wins():
    p = T.parse_supervisor_log("\n".join([START, OPEN, ATTEMPT1, WAIT, ATTEMPT2, COMPLETED]))
    assert p["state"] == "completed"
    assert p["attempt"] == 2


def test_state_gave_up():
    assert T.parse_supervisor_log("\n".join([START, ATTEMPT1, GAVEUP]))["state"] == "gave-up"
    assert T.parse_supervisor_log("\n".join([START, WAIT, RAM_ABORT]))["state"] == "gave-up"


def test_state_stopped_clean():
    assert T.parse_supervisor_log("\n".join([START, WAIT, STOPPED]))["state"] == "stopped"


def test_unrecognized_log_is_unknown_not_faked():
    assert T.parse_supervisor_log("some other tool's output\nnothing we know")["state"] == "unknown"


# --- checkpoint step ------------------------------------------------------------

def test_latest_checkpoint_step_from_dir_names(tmp_path):
    for n in (50, 100, 2020):
        (tmp_path / f"checkpoint-{n}").mkdir()
    assert T.latest_checkpoint_step(tmp_path) == 2020


def test_checkpoint_step_falls_back_to_trainer_state(tmp_path):
    (tmp_path / "trainer_state.json").write_text('{"global_step": 137}', encoding="utf-8")
    assert T.latest_checkpoint_step(tmp_path) == 137


def test_no_checkpoints_is_none(tmp_path):
    assert T.latest_checkpoint_step(tmp_path) is None
    assert T.latest_checkpoint_step(tmp_path / "nope") is None


# --- double-launch guard (pure, fail-safe) --------------------------------------

def test_guard_refuses_when_screen_alive():
    assert T.would_double_launch(screen_is_alive=True, lock_present=False) is True


def test_guard_refuses_when_lock_present():
    assert T.would_double_launch(screen_is_alive=False, lock_present=True) is True


def test_guard_refuses_when_liveness_unprobed():
    # None means we could not confirm the screen is dead -> fail safe, refuse.
    assert T.would_double_launch(screen_is_alive=None, lock_present=False) is True


def test_guard_allows_only_when_provably_clear():
    assert T.would_double_launch(screen_is_alive=False, lock_present=False) is False


# --- path translator ------------------------------------------------------------

def test_path_translator_round_trips():
    assert T.to_wsl("E:\\local-model-run\\logs") == "/mnt/e/local-model-run/logs"
    assert T.to_win("/mnt/e/local-model-run/logs") == "E:\\local-model-run\\logs"
    assert T.to_win(T.to_wsl("E:\\local-model-run")) == "E:\\local-model-run"


# --- status composition + reconcile (liveness = screen, only screen) ------------

def test_status_missing_log_is_stopped(tmp_path):
    s = T.training_status(str(tmp_path), screen_probe=lambda: False)
    assert s["state"] == "stopped"
    assert s["log_present"] is False
    assert s["schema"] == T.SCHEMA


def test_status_liveness_is_the_screen_probe(tmp_path):
    # The status must report exactly what the probe says -- never invent liveness.
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "phase2-32b-supervisor.log").write_text(
        "\n".join([START, OPEN, ATTEMPT1]), encoding="utf-8")
    alive = T.training_status(str(tmp_path), screen_probe=lambda: True)
    dead = T.training_status(str(tmp_path), screen_probe=lambda: False)
    assert alive["screen_alive"] is True
    assert dead["screen_alive"] is False


def test_status_flags_training_but_dead_screen(tmp_path):
    # Falsifier: log says an attempt is in flight but screen is dead -> the status
    # must NOT claim it is alive; reconciled=False surfaces the crash.
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "phase2-32b-supervisor.log").write_text(
        "\n".join([START, OPEN, ATTEMPT1]), encoding="utf-8")
    s = T.training_status(str(tmp_path), screen_probe=lambda: False)
    assert s["state"] == "training"
    assert s["screen_alive"] is False
    assert s["reconciled"] is False


def test_status_flags_stale_screen_on_terminal_state(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "phase2-32b-supervisor.log").write_text(
        "\n".join([START, ATTEMPT1, COMPLETED]), encoding="utf-8")
    s = T.training_status(str(tmp_path), screen_probe=lambda: True)
    assert s["state"] == "completed"
    assert s["reconciled"] is False


def test_status_progress_and_flags(tmp_path):
    ckpt = tmp_path / T.CKPT_REL
    ckpt.mkdir(parents=True)
    (ckpt / "checkpoint-1000").mkdir()
    (tmp_path / T.STOP_REL).write_text("", encoding="utf-8")
    s = T.training_status(str(tmp_path), screen_probe=lambda: None)
    assert s["checkpoint_step"] == 1000
    assert s["progress"] == round(1000 / T.TARGET_STEPS, 4)
    assert s["stop_flag_present"] is True
    assert s["reconciled"] is None            # unprobed liveness -> unreconciled
