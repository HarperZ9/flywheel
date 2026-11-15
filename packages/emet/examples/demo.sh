#!/usr/bin/env sh
# Best-effort demo - not runtime-verified by author.
#
# Drives the real EMET surface end-to-end against a sample input. Uses only real
# membrane.py commands and the public marker corpus. Runs in a scratch directory
# so it writes no state into the repo (anchors.json / *_log.jsonl / *.refused are
# created inside $WORK and are .gitignored anyway).
#
# Usage:  sh examples/demo.sh
#
# Requires: python (3.x), and the membrane.py / corpus.py / verdict.py core.
set -eu

# Resolve repo root from this script's location (examples/ is one level down).
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
SAMPLE="$HERE/sample-prompt.txt"

PY=${PYTHON:-python}
WORK=$(mktemp -d 2>/dev/null || mktemp -d -t emet_demo)
trap 'rm -rf "$WORK"' EXIT

cp "$SAMPLE" "$WORK/prompt.txt"
cp "$SAMPLE" "$WORK/source.txt"
cp "$SAMPLE" "$WORK/view.txt"     # a faithful presented view (identical bytes)
cd "$WORK"

echo "== selftest =="
"$PY" "$REPO/membrane.py" selftest

echo
echo "== anchor + verify (expect MATCH, exit 0) =="
"$PY" "$REPO/membrane.py" anchor prompt.txt
"$PY" "$REPO/membrane.py" verify prompt.txt || echo "(verify exit $?)"

echo
echo "== verify after a one-byte change (expect DRIFT, exit 1) =="
printf 'X' >> prompt.txt
"$PY" "$REPO/membrane.py" verify prompt.txt || echo "(verify exit $? as expected for DRIFT)"

echo
echo "== the same verdict as a machine-readable --json envelope (SPEC s.13) =="
"$PY" "$REPO/membrane.py" verify --json prompt.txt || echo "(verify --json exit $? as expected for DRIFT)"

echo
echo "== coherence: faithful view vs source (expect COHERENT, exit 0) =="
"$PY" "$REPO/membrane.py" coherence source.txt view.txt || echo "(coherence exit $?)"

echo
echo "== refuse: detect + strip in-band authority markers (expect exit 3) =="
"$PY" "$REPO/membrane.py" refuse source.txt || echo "(refuse exit $? as expected when markers found)"
echo "-- neutralized copy (source.txt.refused): --"
cat source.txt.refused

echo
echo "== corroborate: agreement across disjoint read paths =="
"$PY" "$REPO/membrane.py" corroborate source.txt || echo "(corroborate exit $?)"

echo
echo "== audit: recompute the tamper-evident log chain (expect INTACT) =="
"$PY" "$REPO/membrane.py" audit || echo "(audit exit $?)"

echo
echo "Demo complete. Scratch dir $WORK will be removed on exit."
