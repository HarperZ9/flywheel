#!/bin/sh
# Install the flywheel command for this user on macOS or Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/HarperZ9/flywheel/main/install.sh | sh
#
# Makes a private virtual environment, installs flywheel-verify from PyPI into
# it, and links `flywheel` into ~/.local/bin. Needs Python 3.11 or newer. Nothing
# outside those two folders is changed. Settings:
#   FLYWHEEL_VERSION=1.6.0   install that version (default: latest)
#   FLYWHEEL_SOURCE=path     install from a checkout or wheel instead of PyPI
#   FLYWHEEL_INSTALL_DIR     where the environment goes
#   FLYWHEEL_BIN_DIR         where the command is linked
# To remove: rm -rf "$FLYWHEEL_INSTALL_DIR" "$FLYWHEEL_BIN_DIR/flywheel"
set -eu

DEST="${FLYWHEEL_INSTALL_DIR:-$HOME/.local/share/flywheel/venv}"
BIN="${FLYWHEEL_BIN_DIR:-$HOME/.local/bin}"

PY=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo "flywheel needs Python 3.11 or newer; install it and run this again." >&2
  exit 1
fi

if [ -n "${FLYWHEEL_SOURCE:-}" ]; then
  REQ="$FLYWHEEL_SOURCE"
elif [ -n "${FLYWHEEL_VERSION:-}" ]; then
  REQ="flywheel-verify==$FLYWHEEL_VERSION"
else
  REQ="flywheel-verify"
fi

echo "Installing $REQ with $($PY --version) into $DEST"
"$PY" -m venv "$DEST"
"$DEST/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade "$REQ"
mkdir -p "$BIN"
ln -sf "$DEST/bin/flywheel" "$BIN/flywheel"
"$BIN/flywheel" --version

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "Add $BIN to your PATH to run flywheel from any folder, for example:"
     echo "  echo 'export PATH=\"$BIN:\$PATH\"' >> ~/.profile" ;;
esac
echo "Next: flywheel doctor, then flywheel code in a project folder."
