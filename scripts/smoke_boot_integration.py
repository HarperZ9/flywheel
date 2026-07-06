"""End-to-end integration smoke: boot -> hydrate -> propose -> envelope carries receipt.
Not a unit test; a one-shot demonstration that the full path runs against the
real project tree. Run: py scripts/smoke_boot_integration.py
"""
import json
from harness.task import load_task
from harness.loop import run_loop
from harness.proposer import StubProposer
from harness.oracle import PytestOracle
from harness.boot import boot

CORRECT = "def add(a, b):\n    return a + b\n"

task = load_task("tasks/example_pass",
                 workdir="C:/Users/Zain/AppData/Local/Temp/boot-smoke")
pkt = boot("C:/dev/local-model", budget=1500, focus="example_pass")
print("BOOT verdict:", pkt.verdict, "| root_hash:", pkt.root_hash,
      "| files:", pkt.summary.get("source_files"),
      "| tokens~:", pkt.packet_tokens_approx)
print("BOOT phase_line:", pkt.summary.get("phase_line", "")[:70])

r = run_loop(task, StubProposer(CORRECT), PytestOracle(),
             envelopes_dir="C:/Users/Zain/AppData/Local/Temp/boot-enves",
             boot_packet=pkt)
print("LOOP accepted:", r.accepted, "| oracle:", r.oracle.verdict(),
      "| witness:", r.witness.verdict)
print("ENVELOPE injected_context:", json.dumps(r.envelope.injected_context))
