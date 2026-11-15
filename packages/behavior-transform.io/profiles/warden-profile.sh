#!/usr/bin/env bash
# warden-profile.sh - IO Channel shell integration for Bash / Zsh / Git Bash
#
# Sources the safe_* channel passthrough for WARDEN CLI, Claude Code, Codex.
# Architecture: [A -> io_channel.py -> CLI/Harness -> io_channel.py -> B]
#
# To activate in Bash, add to ~/.bashrc:
#   source ~/AGENTS/warden_shell/tools/warden-profile.sh
#
# To activate in Zsh, add to ~/.zshrc:
#   source ~/AGENTS/warden_shell/tools/warden-profile.sh

WARDEN_TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/tools"
IO_CHANNEL="${WARDEN_TOOLS}/io_channel.py"
IO_MODE="${WARDEN_TOOLS}/io_mode.py"
: "${WARDEN_IO_CHANNEL:=$(python "${IO_MODE}" status --mode-only 2>/dev/null || printf on)}"
export WARDEN_IO_CHANNEL

# --- Session IO mode ---------------------------------------------------------

io-on() {
    WARDEN_IO_CHANNEL="$(python "${IO_MODE}" on --mode-only)"
    export WARDEN_IO_CHANNEL
    export WARDEN_IO="${WARDEN_IO_CHANNEL}"
    echo "WARDEN IO Channel: on" >&2
}

io-off() {
    WARDEN_IO_CHANNEL="$(python "${IO_MODE}" off --mode-only)"
    export WARDEN_IO_CHANNEL
    export WARDEN_IO="${WARDEN_IO_CHANNEL}"
    echo "WARDEN IO Channel: off" >&2
}

io-status() {
    python "${IO_MODE}" status >&2
}

# --- Core wrapper ------------------------------------------------------------

io_channel() {
    python "${IO_CHANNEL}" -- "${@}"
}

# --- CLI wrappers ------------------------------------------------------------

warden_wrapped() { python "${IO_CHANNEL}" -- warden "${@}"; }
claude_wrapped() { python "${IO_CHANNEL}" -- claude "${@}"; }
codex_wrapped()  { python "${IO_CHANNEL}" -- codex  "${@}"; }

# --- Direct safe_* shortcuts -------------------------------------------------

safe_read()  { python "${WARDEN_TOOLS}/safe_read.py"  "${@}"; }
safe_write() { python "${WARDEN_TOOLS}/safe_write.py" "${@}"; }
safe_exec()  { python "${WARDEN_TOOLS}/safe_exec.py"  -- "${@}"; }
safe_fetch() { python "${WARDEN_TOOLS}/safe_fetch.py" "${@}"; }
safe_input() { python "${WARDEN_TOOLS}/safe_input.py" "${@}"; }

# --- Aliases (only shadow if native exists) ----------------------------------

if command -v warden &>/dev/null; then alias warden='warden_wrapped'; fi
if command -v claude &>/dev/null; then alias claude='claude_wrapped'; fi
if command -v codex  &>/dev/null; then alias codex='codex_wrapped';   fi

echo "WARDEN IO Channel loaded (${WARDEN_IO_CHANNEL})." >&2
# --- Container ecosystem entry point -----------------------------------------

container() { python "${WARDEN_TOOLS}/container_ecosystem.py" "${@}"; }
