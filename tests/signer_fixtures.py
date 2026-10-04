"""Start a real signer process for a test, with a home the test's agent side never
touches. Signing needs cryptography or pynacl; callers importorskip first."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def new_address() -> str:
    if sys.platform == "win32":
        return "\\\\.\\pipe\\fw-signer-test-" + uuid.uuid4().hex[:12]
    # AF_UNIX paths are capped near 104 bytes on macOS; pytest's tmp_path is long.
    return os.path.join(tempfile.mkdtemp(prefix="fws", dir="/tmp"), "s.sock")


class RunningSigner:
    def __init__(self, signer_home: Path, address: str = "") -> None:
        self.home = Path(signer_home)
        self.address = address or new_address()
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        env.pop("FLYWHEEL_SIGNER", None)
        subprocess.run([sys.executable, "-m", "harness.signer", "init", "--home",
                        str(self.home)], check=True, env=env, cwd=ROOT,
                       capture_output=True)
        self.public_hex = (self.home / "signer-ed25519.pub").read_text().strip()
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "harness.signer", "serve", "--home", str(self.home),
             "--address", self.address], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        line = self.proc.stdout.readline()
        if not line or not json.loads(line).get("ready"):
            self.stop()
            raise RuntimeError(f"signer did not start: {self.proc.stderr.read()}")

    def client(self, pinned: str | None = None):
        from harness.signer.client import SignerClient
        return SignerClient(self.address, self.public_hex if pinned is None else pinned)

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(timeout=10)
        for stream in (self.proc.stdout, self.proc.stderr):
            if stream:
                stream.close()
