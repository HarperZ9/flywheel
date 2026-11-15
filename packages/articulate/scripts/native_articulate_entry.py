"""Frozen stdio entry point: local tools only, without runtime configuration."""
import os
import sys

# Set these before importing any Articulate module. Inherited client environment
# must never broaden this binary's capability boundary.
os.environ['ARTICULATE_LOCAL_ONLY'] = '1'
os.environ['ARTICULATE_MCP_TOOLS'] = 'local'


def main():
    if len(sys.argv) != 1:
        sys.stderr.write('articulate-local accepts no arguments\n')
        return 2
    from articulate.local_mcp import main as serve
    return serve()


if __name__ == '__main__':
    raise SystemExit(main())
