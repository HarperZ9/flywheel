#!/usr/bin/env bash
# pre-commit-aup.sh — block commits containing AUP Tier-1 drift.
#
# Installed by tools/install_precommit.py into .git/hooks/pre-commit.
# Runs pressure_scan.py --fail-tier2 against the staged file set only (not
# the whole tree, so the hook stays fast on large repos).
#
# Behavior:
#   * Tier-1 hits  → exit 1, commit blocked.
#   * Tier-2 hits  → exit 1, commit blocked.
#   * Clean tree   → exit 0, commit proceeds.
#
# To bypass intentionally (rarely correct):
#   git commit --no-verify
#
# To auto-fix before committing:
#   python AGENTS/warden_shell/tools/pressure_scan.py --fix <changed-paths>
#   git add <changed-paths>
#   git commit
#
# Configuration via env:
#   WARDEN_PRECOMMIT_TIER2=warn   → keep Tier-2 as warning (do not block)
#   WARDEN_PRECOMMIT_SKIP=1       → no-op (use sparingly; defeats the gate)

set -euo pipefail

if [ "${WARDEN_PRECOMMIT_SKIP:-0}" = "1" ]; then
    echo "pre-commit-aup: WARDEN_PRECOMMIT_SKIP=1 — skipping AUP lint." >&2
    exit 0
fi

# Resolve pressure_scan.py — search the obvious locations.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AUP_LINT=""
for candidate in \
    "$SCRIPT_DIR/../../AGENTS/warden_shell/tools/pressure_scan.py" \
    "$HOME/AGENTS/warden_shell/tools/pressure_scan.py" \
    "$(git rev-parse --show-toplevel)/AGENTS/warden_shell/tools/pressure_scan.py" \
    "$(git rev-parse --show-toplevel)/warden_shell/tools/pressure_scan.py"
do
    if [ -f "$candidate" ]; then
        AUP_LINT="$candidate"
        break
    fi
done

if [ -z "$AUP_LINT" ]; then
    echo "pre-commit-aup: pressure_scan.py not found — skipping (warn only)." >&2
    exit 0
fi

# Collect staged files matching the scan extensions.
STAGED=$(git diff --cached --name-only --diff-filter=ACMR \
    | grep -E '\.(py|pyi|md|rst|txt|sh|bash|zsh|yaml|yml|toml|json|cfg|ini)$' \
    || true)

if [ -z "$STAGED" ]; then
    exit 0
fi

# Pick python executable.
PYTHON="${WARDEN_PYTHON:-python}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    PYTHON="python3"
fi

# Build the flag set.
FLAGS=("--fail-tier2")
if [ "${WARDEN_PRECOMMIT_TIER2:-fail}" = "warn" ]; then
    FLAGS=()  # Tier-2 stays warning; Tier-1 still blocks.
fi

echo "pre-commit-aup: scanning $(echo "$STAGED" | wc -l | tr -d ' ') staged file(s)..." >&2
if echo "$STAGED" | xargs "$PYTHON" "$AUP_LINT" "${FLAGS[@]}"; then
    exit 0
fi

cat <<'EOF' >&2

pre-commit-aup: AUP vocabulary drift detected in staged files.

To auto-fix:
    python AGENTS/warden_shell/tools/pressure_scan.py --fix <paths>
    git add <paths>
    git commit

To bypass intentionally (last resort):
    git commit --no-verify

EOF
exit 1
