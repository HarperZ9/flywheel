"""Run the real gateway with a fixture-owned home pointer for Flutter tests."""
from pathlib import Path
import sys


def main():
    fixture_home, port, repo = sys.argv[1:]
    sys.path.insert(0, repo)
    from harness.capture_hooks import home
    from harness import gateway_endpoint_file, gateway

    # Environment-only home changes do not isolate the OS-known-folder pointer.
    # Patch both references in this test child; production lookup stays unchanged.
    pointer = Path(fixture_home) / "fixture-pointer.json"
    home.pointer_path = lambda: pointer
    gateway_endpoint_file.pointer_path = lambda: pointer
    return gateway.main(["--port", port, "--root", repo])


if __name__ == "__main__":
    raise SystemExit(main())
