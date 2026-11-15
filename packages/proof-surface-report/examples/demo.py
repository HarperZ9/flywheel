"""Best-effort demo - not runtime-verified by author.

End-to-end walkthrough of the proof-surface-report public API using only the
artifacts bundled in this directory and only functions that the package exports.

Run from a development checkout (the ``proof-surface`` contract package must be
importable):

    PYTHONPATH=src python examples/demo.py

or, after ``pip install``:

    python examples/demo.py

The script prints a rendered report, demonstrates per-file shape detection, and
shows that an authority-shaped title is rejected.
"""
from __future__ import annotations

from pathlib import Path

from proof_surface_report import load_artifact, render_report

EXAMPLES = Path(__file__).resolve().parent
ARTIFACTS = [
    EXAMPLES / "public-surface.packet.json",
    EXAMPLES / "provenance.packet.json",
    EXAMPLES / "emet.receipt.json",
]


def main() -> int:
    # 1. Detect each artifact's shape ("packet" or "witness_receipt").
    print("# Detected artifact kinds\n")
    for path in ARTIFACTS:
        kind, _data = load_artifact(path)
        print(f"- {path.name}: {kind}")
    print()

    # 2. Render all artifacts into a single Markdown handoff report.
    report = render_report("Proof Surface Handoff Report", ARTIFACTS)
    print(report)
    print()

    # 3. Show that an authority-shaped title is rejected before rendering.
    print("# Authority-title guard\n")
    try:
        render_report("Certified Safe Report", ARTIFACTS[:1])
    except ValueError as exc:
        print(f"- rejected as expected: {exc}")
    else:  # pragma: no cover - demo guard
        print("- WARNING: authority-shaped title was not rejected")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
