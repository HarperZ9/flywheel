#!/usr/bin/env bash
# Set up the Flywheel record signer as its own Linux user, under systemd.
#
# Run as root:  sudo scripts/signer/setup_linux.sh /path/to/python
#
# The python given must import flywheel's `harness` package and a signing
# backend (pip install "flywheel-verify[signing]"), and must be readable by
# the new user (a system or /opt install, not one under a private home).
#
# What it creates:
#   user   flywheel-signer   (system account, no login shell)
#   home   /var/lib/flywheel-signer   mode 0700, owner flywheel-signer: seed, journal
#   socket /run/flywheel-signer/signer.sock   in a 0755 directory the agent cannot write
#   unit   flywheel-signer.service
#
# It prints the two environment variables the agent's hook needs. Nothing here
# copies, prints or moves the private seed.
set -euo pipefail

PY="${1:?usage: setup_linux.sh /path/to/python}"
USER_NAME="flywheel-signer"
HOME_DIR="/var/lib/flywheel-signer"
RUN_DIR="/run/flywheel-signer"
SOCK="$RUN_DIR/signer.sock"
UNIT="/etc/systemd/system/flywheel-signer.service"

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root: the signer user and its home need root to create" >&2
  exit 1
fi
if ! "$PY" -c "import harness.signer.keys" 2>/dev/null; then
  echo "$PY cannot import harness.signer; install flywheel into it first" >&2
  exit 1
fi

if ! id "$USER_NAME" >/dev/null 2>&1; then
  useradd --system --home-dir "$HOME_DIR" --no-create-home \
    --shell /usr/sbin/nologin "$USER_NAME"
fi
install -d -m 700 -o "$USER_NAME" -g "$USER_NAME" "$HOME_DIR"
runuser -u "$USER_NAME" -- "$PY" -m harness.signer init --home "$HOME_DIR" >/dev/null

cat > "$UNIT" <<UNIT
[Unit]
Description=Flywheel record signer (separate identity from the agent)
After=local-fs.target

[Service]
User=$USER_NAME
Group=$USER_NAME
RuntimeDirectory=flywheel-signer
RuntimeDirectoryMode=0755
ExecStart=$PY -m harness.signer serve --home $HOME_DIR --address $SOCK
Restart=on-failure
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$HOME_DIR
PrivateTmp=yes
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now flywheel-signer.service

for _ in $(seq 1 50); do [ -S "$SOCK" ] && break; sleep 0.1; done
PUB="$(runuser -u "$USER_NAME" -- "$PY" -m harness.signer pubkey --home "$HOME_DIR")"

cat <<DONE
flywheel-signer is running as $USER_NAME.

Give the agent's hook these two variables (for example in the harness
settings or the shell profile that launches the agent):

  export FLYWHEEL_SIGNER=$SOCK
  export FLYWHEEL_SIGNER_PUBKEY=$PUB

Pin the same key when you verify, from your own shell:

  flywheel monitor verify <home> --trust-root $PUB

Check the boundary: as the agent's user, this must fail with Permission denied:

  cat $HOME_DIR/signer-ed25519.seed
DONE
