#!/bin/sh
# Re-run every leg of the report from a fresh clone.
#
#   sh scripts/run_all.sh OUT_DIR [BOOTLOOPS_CHECKOUT]
#
# Needs: git, Python 3.12, node, curl, sha256sum, and elan with Lean v4.34.1.
# If BOOTLOOPS_CHECKOUT is omitted, BootLoops is cloned into OUT_DIR and
# checked out at the pinned commit. Set SKIP_LEAN=1 to skip the Lean legs
# (they download Mathlib, several GB), SKIP_SCALE=1 to skip only the scale series,
# and SKIP_FUZZ=1 to skip the differential fuzzer.
set -eu
OUT=${1:?usage: run_all.sh OUT_DIR [BOOTLOOPS_CHECKOUT]}
REPO=$(cd "$(dirname "$0")/.." && pwd)
BL_COMMIT=66b680ce742e654cfe86da4f072a69061fe182b1
mkdir -p "$OUT"

if [ $# -ge 2 ]; then BL=$2; else
  BL="$OUT/bootloops"
  [ -d "$BL/.git" ] || git clone -q https://github.com/BootLoops-ai/bootloops.git "$BL"
  git -C "$BL" checkout -q "$BL_COMMIT"
fi
test "$(git -C "$BL" rev-parse HEAD)" = "$BL_COMMIT" || { echo "BootLoops is not at the pinned commit"; exit 2; }
# Hash the committed bytes (git blobs), not the working tree: a Windows checkout
# with core.autocrlf=true rewrites line endings and changes the hashes.
for f in WITNESS_FORMAT.md core.py receipt.py emitter.py; do
  printf '%s *%s
' "$(git -C "$BL" show "$BL_COMMIT:tools/trust/receipt/$f" | sha256sum | cut -d' ' -f1)" "$f"
done > "$OUT/bootloops-pins.sha256"
diff "$OUT/bootloops-pins.sha256" "$REPO/inputs/bootloops-pins.sha256"

python -m venv "$OUT/venv"
if [ -x "$OUT/venv/bin/python" ]; then PY="$OUT/venv/bin/python"; else PY="$OUT/venv/Scripts/python"; fi
"$PY" -m pip install -q -r "$REPO/requirements.txt"

cd "$REPO"
"$PY" -m pytest -q tests
"$PY" scripts/gen_corpus.py "$BL" "$OUT/corpus"
"$PY" scripts/compare.py "$BL" "$OUT/corpus" "$OUT/results"
"$PY" scripts/controls.py "$BL" "$OUT/corpus" "$OUT/results" 20261002
"$PY" scripts/edge_cases.py "$BL" "$OUT/corpus" "$OUT/edge"
"$PY" scripts/compare_third.py "$OUT/corpus" "$OUT/third"
[ "${SKIP_FUZZ:-0}" = 1 ] || "$PY" scripts/fuzz.py "$BL" "$OUT/fuzz" --seed 20261002
"$PY" scripts/cli_probe.py "$BL" "$OUT/cli_probe"

# Replay of the published sunrise check (bootloops.ai), pinned by hash
mkdir -p "$OUT/replay" && cd "$OUT/replay"
curl -sfL -o sunrise-bundle.zip https://bootloops.ai/files/sunrise/sunrise-bundle.zip
sha256sum -c "$REPO/inputs/sunrise.sha256"
"$PY" -c "import zipfile; zipfile.ZipFile('sunrise-bundle.zip').extractall('.')"
cd sunrise-bundle
sha256sum -c MANIFEST.sha256
"$PY" sunrise-evaluate.py --point -3 --point -9 --point 12 | tee "$OUT/replay/evaluate.out"
"$PY" sunrise-B34.py --dps 60 | tee "$OUT/replay/b34.out"
cd "$REPO"
"$PY" scripts/sunrise_quadrature.py 30 | tee "$OUT/replay/quadrature.out"

if [ "${SKIP_LEAN:-0}" != 1 ]; then
  (cd lean && lake exe cache get)
  "$PY" scripts/lean_run.py "$OUT/corpus" "$OUT/lean" --per-corpus 2 --rows-per-module 6 --linear-max-terms 100
  [ "${SKIP_SCALE:-0}" = 1 ] || "$PY" scripts/lean_run.py "$OUT/corpus" "$OUT/lean_scale" --only-scale
  "$PY" scripts/lean_reflect.py "$OUT/corpus" "$OUT/lean_reflect" --jobs "${LEAN_JOBS:-4}"     --sizes "${REFLECT_SIZES:-10000,30000,100000,300000}"
fi
"$PY" scripts/summarize.py "$OUT"
