"""plexus.runner: the part of Plexus that starts programs.

fanout runs tools, budget limits them, mcp_call talks to one MCP server. The
rest of Plexus reads manifests and returns answers; this subpackage is kept
apart so the read-only MCP server and the directory plugin never import it.
"""
