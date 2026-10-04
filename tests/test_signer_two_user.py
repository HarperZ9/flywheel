"""The OS boundary itself: the signer as a second Linux user, the test as the agent.

Runs only where FLYWHEEL_SIGNER_TWO_USER=1 (the CI job "signer, two OS users"
on ubuntu, which has passwordless sudo). There a skip would hide the one test
that exercises the boundary, so preconditions are assertions, not skips.

Success criteria: the agent's user cannot read the seed, list the signer's
home, write the socket directory, or rewind the journal; every attestation it
gets says separate-identity with the two uids the kernel reported; the verifier
reports MATCH with no same-identity warning; a rechained edit is DRIFT.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(
    os.environ.get("FLYWHEEL_SIGNER_TWO_USER") != "1",
    reason="needs a second OS user and sudo; the CI two-user job sets FLYWHEEL_SIGNER_TWO_USER=1")

USER = "fwsigner-test"
HOME = "/tmp/fwsigner-home"
RUN = "/tmp/fwsigner-run"
ADDRESS = RUN + "/s.sock"


def _sudo(*args, check=True):
    return subprocess.run(["sudo", "-n", *args], check=check, capture_output=True, text=True)


def _as_signer(src, *args):
    return ["sudo", "-n", "-u", USER, "env", f"PYTHONPATH={src}", sys.executable,
            "-m", "harness.signer", *args]


@pytest.fixture(scope="module")
def signer():
    assert sys.platform.startswith("linux"), "the two-user test is Linux only"
    assert os.geteuid() != 0, "run as an ordinary user, or the boundary is moot"
    src = Path(tempfile.mkdtemp(prefix="fwsrc"))
    os.chmod(src, 0o755)
    shutil.copytree(ROOT / "harness", src / "harness")
    _sudo("useradd", "--system", "--no-create-home", "--shell", "/usr/sbin/nologin",
          USER, check=False)
    _sudo("rm", "-rf", HOME, RUN)
    _sudo("install", "-d", "-m", "700", "-o", USER, HOME)
    _sudo("install", "-d", "-m", "755", "-o", USER, RUN)
    subprocess.run(_as_signer(src, "init", "--home", HOME), check=True, capture_output=True)
    public = subprocess.run(_as_signer(src, "pubkey", "--home", HOME), check=True,
                            capture_output=True, text=True).stdout.strip()
    proc = subprocess.Popen(_as_signer(src, "serve", "--home", HOME, "--address", ADDRESS),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert json.loads(proc.stdout.readline())["ready"], proc.stderr.read()
    yield {"public": public, "src": src}
    _sudo("pkill", "-u", USER, check=False)
    proc.wait(timeout=10)


def _client(signer):
    from harness.signer.client import SignerClient
    return SignerClient(ADDRESS, signer["public"])


def test_the_agent_user_cannot_reach_the_key_or_the_journal(signer):
    with pytest.raises(PermissionError):
        open(os.path.join(HOME, "signer-ed25519.seed"), "rb")
    with pytest.raises(PermissionError):
        os.listdir(HOME)
    with pytest.raises(PermissionError):
        open(os.path.join(RUN, "squat.sock"), "w")
    rewind = subprocess.run([sys.executable, "-m", "harness.signer", "rewind", "--home",
                             HOME, "--store", "x"], cwd=ROOT, capture_output=True, text=True)
    assert rewind.returncode == 1, rewind.stderr
    with pytest.raises(PermissionError):
        open(os.path.join(HOME, "journal.json"), "w")


def test_attestations_carry_the_kernel_reported_uids(signer, tmp_path):
    from harness.preaction.records import HoldStore
    from tests.test_signer_forgery import _decision
    store = HoldStore(tmp_path / "home", signer=_client(signer))
    store.append(_decision(0))
    att = json.loads(store.path.read_text().splitlines()[0])["attestation"]
    iso = att["isolation"]
    assert iso["mode"] == "separate-identity", iso
    assert iso["client"] == f"uid:{os.getuid()}" and iso["signer"] != iso["client"]
    assert iso["via"] == "kernel peer credential"


def test_verifier_matches_without_warning_and_catches_a_rechain(signer, tmp_path):
    from harness.preaction.records import HoldStore
    from harness.preaction.verify import verify_store
    from tests.test_signer_forgery import _decision, _rechain, _rows, _write
    store = HoldStore(tmp_path / "home", signer=_client(signer))
    for i in range(3):
        store.append(_decision(i))
    clean = verify_store(tmp_path / "home", trust_root=signer["public"])
    assert clean["verdict"] == "MATCH" and clean["notes"] == []
    assert clean["signer_isolation"] == ["separate-identity"]
    rows = _rows(store)
    rows[2]["decision"] = "APPROVED_ONCE"
    _write(store, _rechain(rows))
    assert verify_store(tmp_path / "home", trust_root=signer["public"])["verdict"] == "DRIFT"
