"""Static lane declarations for the Flywheel lane layer."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Lane:
    """One declared flagship or bundled engine lane."""
    name: str
    install_name: str
    command: str
    mcp_args: tuple[str, ...]
    kind: str                       # "pip" | "npm" | "bundled"
    version: str
    role: str
    organ: str
    source_repo: str = ""           # for the source-checkout install profile
    py_module: str = ""             # `python -m` entry for a pip lane
    extra_source_repos: tuple = ()  # sibling repos this lane imports at runtime; each
    #                                 repo's /src is added to the child PYTHONPATH so a
    #                                 lane that composes uninstalled siblings still probes live

    def mcp_command(self) -> list[str]:
        """The argv that launches this lane's MCP stdio server."""
        return [self.command, *self.mcp_args]


# The lane registry. install_name -> command asymmetry is mapped explicitly
# (pip install gather-engine exposes the `gather` command, etc.). local-model
# is bundled (no install; it IS Flywheel). learn is added here even though
# telos's manifest omits it -- closing a known gap so Flywheel's roster is
# complete.
LANES: dict[str, Lane] = {
    "gather": Lane(
        "gather", "gather-engine", "gather", ("mcp",), "pip", "1.6.1",
        "research intake + provenance receipts (verified-data flywheel intake)",
        "perception", source_repo="public/gather", py_module="gather.cli"),
    "crucible": Lane(
        "crucible", "crucible-bench", "crucible", ("mcp",), "pip", "1.2.0",
        "falsifiable verification + re-check (register -> steelman -> measure -> witness)",
        "verification", source_repo="public/crucible", py_module="crucible.cli"),
    "index": Lane(
        "index", "index-graph", "index", ("mcp",), "pip", "2.9.0",
        "workspace map + symbol graph + verified wiki (the catalog lane)",
        "structure", source_repo="public/index", py_module="index_graph"),
    "forum": Lane(
        "forum", "forum-engine", "forum", ("mcp",), "pip", "1.13.0",
        "witnessed causal ledger + model-agnostic routing",
        "orchestration", source_repo="public/forum", py_module="forum.cli"),
    "learn": Lane(
        "learn", "@harperz9/learn", "node", ("src/mcp.mjs",), "npm", "1.6.0",
        "accountable learning forge (spaced repetition + retrieval practice)",
        "learning", source_repo="public/learn"),
    "telos": Lane(
        "telos", "project-telos-mcp", "node", ("demo/telos-mcp.mjs",), "npm", "0.2.0",
        "the reconciliation lane: five-tool workflow + creative engine + doctors",
        "reconciliation", source_repo="public/telos"),
    "local-model": Lane(
        "local-model", "", "python", ("-m", "harness.local_mcp"), "bundled", "0.1.0",
        "the trained 14B proposer + verified-inference harness (the engine lane)",
        "propose-verify"),
    "relay": Lane(
        "relay", "relay-agent", "relay", ("--mcp",), "pip", "0.1.0",
        "accountable coding agent on any model endpoint (local-first, witnessed runs)",
        "execution", source_repo="public/relay", py_module="relay.local_agent_cli"),
    "plexus": Lane(
        "plexus", "plexus-mesh", "plexus", ("mcp",), "pip", "0.2.0",
        "capability discovery + auto-wiring of the tool mesh (the layer above a flat tool list)",
        "wiring", source_repo="public/plexus", py_module="plexus.cli"),
    "mneme": Lane(
        "mneme", "mneme-memory", "mneme", ("mcp",), "pip", "0.1.0",
        "accountable memory: recall with re-derivable ranking receipts + drift verdicts",
        "memory", source_repo="public/mneme", py_module="mneme.cli"),
    "calibrate-pro": Lane(
        "calibrate-pro", "calibrate-pro", "calibrate-pro", ("mcp",), "pip", "1.1.0",
        "evidence-labeled display calibration: color-target and characterized-panel "
        "catalog + readiness doctor (read-only over MCP; actuation stays GUI-gated)",
        "calibration", source_repo="public/calibrate-pro", py_module="calibrate_pro.main"),
    "accountable-surface": Lane(
        "accountable-surface", "accountable-surface", "accountable-surface-server", (),
        "pip", "0.1.0",
        "live accountability seam: witnessed perception + operator-grant pre-execution "
        "gate + self-verifying effectors + tamper-evident journal (actuates, so T2)",
        "actuation", source_repo="public/accountable-surface",
        py_module="accountable_surface.server",
        extra_source_repos=("public/coherence-membrane", "public/proof-surface")),
}
