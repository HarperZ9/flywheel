"""Read one offline capture and emit a content-minimized Journey review on stdout."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .evidence_json import strict_load_json
from .norvane_capture import import_norvane_capture
from .private_artifact_fs import PrivateArtifactError, open_artifact_root


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_root")
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args(argv)
    try:
        path = Path(args.source_manifest).absolute()
        with open_artifact_root(path.parent, writable=False) as reader:
            manifest = strict_load_json(reader.read_bytes(path.name, max_bytes=65_536))
        result = import_norvane_capture(args.capture_root, manifest,
            imported_at=datetime.now(timezone.utc).isoformat(),
            expected_manifest_sha256=args.expected_manifest_sha256)
    except (OSError, ValueError, PrivateArtifactError):
        print(json.dumps({"error": "capture_input_rejected"}))
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    # Import success never means task verification. Conflicts still emit useful data.
    return 1 if result["issues"] or result["artifact_integrity"] == "mismatch" else 0


if __name__ == "__main__":
    raise SystemExit(main())
