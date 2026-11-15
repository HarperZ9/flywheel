"""The one version number canon reports.

`canon --version`, `canon.__version__`, and the serverInfo of both MCP servers
read it from here. pyproject.toml declares the same number for the package
metadata, and tests/test_local_mcp.py holds the two equal, so a release bumps
this line and the pyproject line together or the suite fails.
"""
from __future__ import annotations

__version__ = "0.7.0"
DISTRIBUTION = "flywheel-canon"
