"""Source and frozen Canon client entrypoint; no installation or ambient grants."""
from pathlib import Path
import sys

if not getattr(sys, 'frozen', False):
    source = Path(__file__).resolve().parent / 'src'
    if not (source / 'canon' / 'client_mcp.py').is_file():
        sys.stderr.write('canon: the server code is missing from the plugin folder. Reinstall the plugin.\n')
        raise SystemExit(1)
    sys.path.insert(0, str(source))

from canon.client_mcp import main

if __name__ == '__main__':
    raise SystemExit(main())
