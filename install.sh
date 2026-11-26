#!/usr/bin/env sh
# Zero-friction 1-command installer for Flywheel (flywheel-verify) with fail-closed SHA256SUMS verification.
# Supports uv tool, pipx, or standalone venv install with zero manual toolchain setup.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/HarperZ9/flywheel/main/install.sh | sh
#   sh install.sh --self-test
set -eu

REPO="HarperZ9/flywheel"
VERSION="${FLYWHEEL_VERSION:-latest}"
INSTALL_DIR="${FLYWHEEL_INSTALL_DIR:-$HOME/.flywheel}"
FROM_DIR="${FLYWHEEL_FROM_DIR:-}"
METHOD="${FLYWHEEL_INSTALL_METHOD:-auto}"
NO_PATH=0
SELF_TEST=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --install-dir) INSTALL_DIR="$2"; shift 2 ;;
    --from-dir) FROM_DIR="$2"; shift 2 ;;
    --method) METHOD="$2"; shift 2 ;;
    --no-path) NO_PATH=1; shift ;;
    --self-test) SELF_TEST=1; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print tolower($1)}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print tolower($1)}'
  else
    echo "Refusing install: sha256sum or shasum is required." >&2
    exit 1
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
  actual="$(sha256_file "$file_path")"
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

install_wheel() {
  wheel="$1"
  target="$2"
  mode="$METHOD"
  if [ "$mode" = "auto" ]; then
    if command -v uv >/dev/null 2>&1; then mode="uv"
    elif command -v pipx >/dev/null 2>&1; then mode="pipx"
    else mode="venv"
    fi
  fi

  case "$mode" in
    uv)
      uv tool install --force "$wheel"
      echo "Flywheel installed via uv tool."
      ;;
    pipx)
      pipx install --force "$wheel"
      echo "Flywheel installed via pipx."
      ;;
    venv)
      py="python3"
      command -v python3 >/dev/null 2>&1 || py="python"
      mkdir -p "$target/bin"
      "$py" -m venv "$target/venv"
      "$target/venv/bin/python" -m pip install --quiet --no-deps --no-index --force-reinstall "$wheel"
      ln -sf "$target/venv/bin/flywheel" "$target/bin/flywheel"
      if [ "$NO_PATH" -eq 0 ] && [ -n "${HOME:-}" ]; then
        for rc in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
          if [ -f "$rc" ] && ! grep -Fq "$target/bin" "$rc"; then
            printf '\nexport PATH="%s/bin:$PATH"\n' "$target" >> "$rc"
          fi
        done
      fi
      echo "Flywheel installed in standalone venv: $target/bin/flywheel"
      ;;
    *)
      echo "Unsupported install method: $mode (use auto, uv, pipx, or venv)" >&2
      return 2
      ;;
  esac
}

install_from_stage() {
  stage="$1"
  target="$2"
  sums="$(find_sums "$stage")" || return 1
  wheel=""
  for cand in "$stage"/flywheel_verify-*.whl; do
    if [ -f "$cand" ]; then wheel="$cand"; break; fi
  done
  [ -n "$wheel" ] || { echo "Refusing install: no flywheel_verify wheel found in $stage." >&2; return 1; }
  verify_checksum "$wheel" "$(basename "$wheel")" "$sums" || return 1
  install_wheel "$wheel" "$target" || return 1
  mkdir -p "$target"
  cp "$sums" "$target/SHA256SUMS"
  echo "Flywheel verified (SHA256SUMS OK)."
}

run_self_test() {
  tmp="$(mktemp -d 2>/dev/null || mktemp -d -t flywheel-selftest)"
  trap 'rm -rf "$tmp"' EXIT INT TERM
  stage="$tmp/stage"
  mkdir -p "$stage"
  whl="$stage/flywheel_verify-0.0.1-py3-none-any.whl"

  python3 -c '
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
  install_from_stage "$stage" "$tmp/dest_ok"
  out="$("$tmp/dest_ok/bin/flywheel")"
  printf '%s\n' "$out" | grep -q "flywheel selftest ok" || { echo "Self-test failed: unexpected CLI output." >&2; exit 1; }

  # Planted 1-byte tamper control: must fail closed before installing.
  python3 -c '
import sys
p = sys.argv[1]
b = bytearray(open(p, "rb").read())
b[-1] ^= 0x01
open(p, "wb").write(b)
' "$whl"

  if install_from_stage "$stage" "$tmp/dest_bad" >/dev/null 2>&1; then
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

if [ -n "$FROM_DIR" ]; then
  install_from_stage "$FROM_DIR" "$INSTALL_DIR"
  exit 0
fi

if [ "$VERSION" = "latest" ]; then
  api="https://api.github.com/repos/$REPO/releases/latest"
else
  case "$VERSION" in v*) tag="$VERSION" ;; *) tag="v$VERSION" ;; esac
  api="https://api.github.com/repos/$REPO/releases/tags/$tag"
fi

tmp="$(mktemp -d 2>/dev/null || mktemp -d -t flywheel-install)"
trap 'rm -rf "$tmp"' EXIT INT TERM
meta="$tmp/release.json"
curl -fsSL -H "Accept: application/vnd.github+json" -H "User-Agent: flywheel-installer" "$api" -o "$meta"

urls="$(python3 -c '
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
install_from_stage "$tmp" "$INSTALL_DIR"
