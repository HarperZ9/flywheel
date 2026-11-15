#!/usr/bin/env python
"""
Block Secrets Hook - PreToolUse
Prevents assistants and automation tools from reading or editing sensitive
files. Exit code 2 blocks the operation.
"""
import json
import sys
from pathlib import Path

# Files that should never be read or edited by assistants or automation
# tools (basename match - anchored).
SENSITIVE_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    ".env.development",
    "secrets.json",
    "secrets.yaml",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "service-account.json",
}

# Path components (between separators) that mark sensitive directories.
# Anchored to path parts, not substrings, so workspace Python modules whose
# names contain "private_key", "secret_key", or "ssh" are not blocked, while
# real OS credential dirs still are.
SENSITIVE_PATH_COMPONENTS = {
    ".ssh",
    ".aws",
    ".gnupg",
    ".docker",
}

try:
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name", "")
    file_path = data.get("tool_input", {}).get("file_path", "")

    if not file_path:
        sys.exit(0)

    path = Path(file_path)

    # Allow Write to .env files for project scaffolding. Only block Read/Edit,
    # which could leak existing secrets.
    if tool_name == "Write" and path.name.startswith(".env"):
        sys.exit(0)

    if path.name in SENSITIVE_FILENAMES:
        print(
            f"BLOCKED: Access to '{file_path}' denied. This is a sensitive file.",
            file=sys.stderr,
        )
        sys.exit(2)

    for component in SENSITIVE_PATH_COMPONENTS:
        if component in path.parts:
            print(
                "BLOCKED: Access to "
                f"'{file_path}' denied. Path contains sensitive component "
                f"'{component}'.",
                file=sys.stderr,
            )
            sys.exit(2)

    sys.exit(0)

except Exception as exc:
    print(f"Hook error: {exc}", file=sys.stderr)
    sys.exit(1)
