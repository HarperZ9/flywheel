#!/bin/sh
# Install the flywheel command for this user on macOS or Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/HarperZ9/flywheel/main/install.sh | sh
#
# Fetches the release wheel + SHA256SUMS from GitHub Releases, verifies SHA-256
# fail-closed before installing, and installs via uv tool, pipx, or a private
# virtual environment (linking `flywheel` into ~/.local/bin). Needs Python 3.11+.
# Settings:
#   FLYWHEEL_VERSION=2.0.0   install that version (default: latest)
#   FLYWHEEL_SOURCE=path     install from a local checkout or wheel
#   FLYWHEEL_FROM_DIR=dir    install a release wheel + SHA256SUMS from a local dir
#   FLYWHEEL_INSTALL_METHOD  auto | uv | pipx | venv (default: auto)
#   FLYWHEEL_INSTALL_DIR     where the environment goes
#   FLYWHEEL_BIN_DIR         where the command is linked
#   FLYWHEEL_FROM_PYPI=1     install flywheel-verify directly from PyPI
set -eu

REPO="HarperZ9/flywheel"
VERSION="${FLYWHEEL_VERSION:-latest}"
DEST="${FLYWHEEL_INSTALL_DIR:-$HOME/.local/share/flywheel/venv}"
BIN="${FLYWHEEL_BIN_DIR:-$HOME/.local/bin}"
FROM_DIR="${FLYWHEEL_FROM_DIR:-}"
METHOD="${FLYWHEEL_INSTALL_METHOD:-auto}"
FROM_PYPI="${FLYWHEEL_FROM_PYPI:-0}"
NO_PATH=0
SELF_TEST=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --install-dir) DEST="$2"; shift 2 ;;
    --bin-dir) BIN="$2"; shift 2 ;;
    --from-dir) FROM_DIR="$2"; shift 2 ;;
    --method) METHOD="$2"; shift 2 ;;
    --from-pypi) FROM_PYPI=1; shift ;;
    --no-path) NO_PATH=1; shift ;;
    --self-test) SELF_TEST=1; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

find_python311() {
  for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>/dev/null; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  echo "flywheel needs Python 3.11 or newer; install it and run this again." >&2
  return 1
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print tolower($1)}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print tolower($1)}'
  else
    echo "Refusing install: sha256sum or shasum is required." >&2
    return 1
  fi
}

expected_hash() {
  awk -v target="$2" '
    {
      h = tolower($1)
      name = $2
      sub(/^\*/, "", name)
      if (name == target && h ~ /^[0-9a-f]{64}$/) { print h; exit 0 }
    }
  ' "$1"
}

verify_checksum() {
  file_path="$1"
  asset_name="$2"
  sums_file="$3"
  expected="$(expected_hash "$sums_file" "$asset_name")"
  if [ -z "$expected" ]; then
    echo "Refusing install: $asset_name is missing from SHA256SUMS." >&2
    return 1
  fi
  actual="$(sha256_file "$file_path")" || return 1
  if [ "$actual" != "$expected" ]; then
    echo "Refusing install: SHA-256 mismatch for $asset_name (expected $expected, got $actual)." >&2
    return 1
  fi
}

find_sums() {
  for cand in SHA256SUMS python-SHA256SUMS.txt SHA256SUMS.txt; do
    if [ -f "$1/$cand" ]; then printf '%s\n' "$1/$cand"; return 0; fi
  done
  echo "Refusing install: SHA256SUMS not found in $1." >&2
  return 1
}

install_venv() {
  spec="$1"
  target_venv="$2"
  target_bin="$3"
  offline="$4"
  py="$(find_python311)" || return 1
  mkdir -p "$(dirname "$target_venv")" "$target_bin"
  "$py" -m venv "$target_venv"
  if [ "$offline" -eq 1 ]; then
    "$target_venv/bin/python" -m pip install --quiet --disable-pip-version-check --no-deps --no-index --force-reinstall "$spec"
  else
    "$target_venv/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade "$spec"
  fi
  ln -sf "$target_venv/bin/flywheel" "$target_bin/flywheel"
  if [ "$NO_PATH" -eq 0 ] && [ -n "${HOME:-}" ]; then
    for rc in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
      if [ -f "$rc" ] && ! grep -Fq "$target_bin" "$rc"; then
        printf '\nexport PATH="%s:$PATH"\n' "$target_bin" >> "$rc"
      fi
    done
  fi
}

install_wheel() {
  wheel="$1"
  target_venv="$2"
  target_bin="$3"
  mode="$METHOD"
  if [ "$mode" = "auto" ]; then
    if command -v uv >/dev/null 2>&1; then mode="uv"
    elif command -v pipx >/dev/null 2>&1; then mode="pipx"
    else mode="venv"
    fi
  fi
  case "$mode" in
    uv) uv tool install --force "$wheel" ;;
    pipx) pipx install --force "$wheel" ;;
    venv) install_venv "$wheel" "$target_venv" "$target_bin" 1 ;;
    *) echo "Unsupported install method: $mode" >&2; return 2 ;;
  esac
}

install_from_stage() {
  stage="$1"
  target_venv="$2"
  target_bin="$3"
  sums="$(find_sums "$stage")" || return 1
  wheel=""
  for cand in "$stage"/flywheel_verify-*.whl; do
    if [ -f "$cand" ]; then wheel="$cand"; break; fi
  done
  [ -n "$wheel" ] || { echo "Refusing install: no flywheel_verify wheel found in $stage." >&2; return 1; }
  verify_checksum "$wheel" "$(basename "$wheel")" "$sums" || return 1
  install_wheel "$wheel" "$target_venv" "$target_bin" || return 1
  mkdir -p "$target_venv"
  cp "$sums" "$target_venv/SHA256SUMS"
  echo "Flywheel verified (SHA256SUMS OK)."
}

run_self_test() {
  py="$(find_python311)" || exit 1
  tmp="$(mktemp -d 2>/dev/null || mktemp -d -t flywheel-selftest)"
  trap 'rm -rf "$tmp"' EXIT INT TERM
  stage="$tmp/stage"
  mkdir -p "$stage"
  whl="$stage/flywheel_verify-0.0.1-py3-none-any.whl"

  "$py" -c '
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr("flywheel_selftest/__init__.py", "VERSION = \"0.0.1\"\n")
    z.writestr("flywheel_selftest/cli.py", "def main():\n    print(\"flywheel selftest ok\")\n")
    z.writestr("flywheel_verify-0.0.1.dist-info/METADATA", "Metadata-Version: 2.1\nName: flywheel-verify\nVersion: 0.0.1\n")
    z.writestr("flywheel_verify-0.0.1.dist-info/WHEEL", "Wheel-Version: 1.0\nGenerator: selftest\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
    z.writestr("flywheel_verify-0.0.1.dist-info/entry_points.txt", "[console_scripts]\nflywheel = flywheel_selftest.cli:main\n")
    z.writestr("flywheel_verify-0.0.1.dist-info/RECORD", "")
' "$whl"

  printf '%s  flywheel_verify-0.0.1-py3-none-any.whl\n' "$(sha256_file "$whl")" > "$stage/SHA256SUMS"

  METHOD="venv"
  NO_PATH=1
  install_from_stage "$stage" "$tmp/dest_ok/venv" "$tmp/dest_ok/bin"
  out="$("$tmp/dest_ok/bin/flywheel")"
  printf '%s\n' "$out" | grep -q "flywheel selftest ok" || { echo "Self-test failed: unexpected CLI output." >&2; exit 1; }

  "$py" -c '
import sys
p = sys.argv[1]
b = bytearray(open(p, "rb").read())
b[-1] ^= 0x01
open(p, "wb").write(b)
' "$whl"

  if install_from_stage "$stage" "$tmp/dest_bad/venv" "$tmp/dest_bad/bin" >/dev/null 2>&1; then
    echo "Self-test failed: tampered wheel was not refused." >&2
    exit 1
  fi
  [ ! -e "$tmp/dest_bad/bin/flywheel" ] || { echo "Self-test failed: tampered wheel installed." >&2; exit 1; }
  echo "SELFTEST PASS: valid wheel install verified and planted 1-byte tamper refused."
}

if [ "$SELF_TEST" -eq 1 ]; then
  run_self_test
  exit 0
fi

if [ -n "${FLYWHEEL_SOURCE:-}" ]; then
  install_venv "$FLYWHEEL_SOURCE" "$DEST" "$BIN" 0
  "$BIN/flywheel" --version
  exit 0
fi

if [ "$FROM_PYPI" = "1" ]; then
  if [ "$VERSION" != "latest" ]; then
    req="flywheel-verify==${VERSION#v}"
  else
    req="flywheel-verify"
  fi
  install_venv "$req" "$DEST" "$BIN" 0
  "$BIN/flywheel" --version
  exit 0
fi

if [ -n "$FROM_DIR" ]; then
  install_from_stage "$FROM_DIR" "$DEST" "$BIN"
  exit 0
fi

if [ "$VERSION" = "latest" ]; then
  api="https://api.github.com/repos/$REPO/releases/latest"
else
  case "$VERSION" in v*) tag="$VERSION" ;; *) tag="v$VERSION" ;; esac
  api="https://api.github.com/repos/$REPO/releases/tags/$tag"
fi

py="$(find_python311)" || exit 1
tmp="$(mktemp -d 2>/dev/null || mktemp -d -t flywheel-install)"
trap 'rm -rf "$tmp"' EXIT INT TERM
meta="$tmp/release.json"
curl -fsSL -H "Accept: application/vnd.github+json" -H "User-Agent: flywheel-installer" "$api" -o "$meta"

urls="$("$py" -c '
import json, re, sys
assets = json.load(open(sys.argv[1], encoding="utf-8")).get("assets", [])
by_name = {a["name"]: a["browser_download_url"] for a in assets}
pick = []
for cand in ("SHA256SUMS", "python-SHA256SUMS.txt", "SHA256SUMS.txt"):
    if cand in by_name:
        pick.append((cand, by_name[cand]))
        break
for n, u in by_name.items():
    if re.match(r"^flywheel_verify-.+\.whl$", n):
        pick.append((n, u))
        break
for n, u in pick:
    print(f"{n}\t{u}")
' "$meta")"

printf '%s\n' "$urls" | while IFS='	' read -r name url; do
  [ -n "$name" ] && curl -fsSL "$url" -o "$tmp/$name"
done
install_from_stage "$tmp" "$DEST" "$BIN"
