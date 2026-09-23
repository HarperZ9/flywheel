"""Static lane declarations for the Flywheel lane layer."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Lane:
    """One declared flagship or bundled engine lane."""
    name: str
    install_name: str
    command: str
    mcp_args: tuple[str, ...]
    kind: str                       # "pip" | "npm" | "bundled" | "http"
    version: str
    role: str
    organ: str
    source_repo: str = ""           # for the source-checkout install profile
    py_module: str = ""             # `python -m` entry for a pip lane
    extra_source_repos: tuple = ()  # sibling repos this lane imports at runtime; each
    #                                 repo's /src is added to the child PYTHONPATH so a
    #                                 lane that composes uninstalled siblings still probes live
    url: str = ""                   # compiled-in default endpoint for a kind="http" lane
    package_disabled_reason: str = ""  # package name is not an admitted distribution

    def mcp_command(self) -> list[str]:
        """The argv that launches this lane's MCP stdio server.

        An http lane has none. It is already running somewhere else, so there is
        nothing to spawn and the honest answer is the empty argv.
        """
        return [] if self.kind == "http" else [self.command, *self.mcp_args]

    def env_url_var(self) -> str:
        """The environment variable that points this lane at its deployment."""
        return f"FLYWHEEL_{self.name.upper().replace('-', '_')}_URL"

    def endpoint(self) -> str:
        """Where an http lane answers. Environment first: which deployment a
        workstation talks to is operator configuration, not a compiled constant."""
        return os.environ.get(self.env_url_var(), self.url)

    def endpoint_detail(self) -> str:
        """What a roster says about a remote lane it has not called."""
        url = self.endpoint()
        return (f"remote lane at {url}; not reached" if url else
                f"remote lane; no endpoint ({self.env_url_var()} unset)")


# The lane registry. install_name -> command asymmetry is mapped explicitly
# (pip install gather-engine exposes the `gather` command, etc.). local-model
# is bundled (no install; it IS Flywheel). learn is added here even though
# telos's manifest omits it -- closing a known gap so Flywheel's roster is
# complete. bulletin is the one lane nobody installs: it runs on the open web,
# so it carries an endpoint instead of an argv. The board is public and needs
# no key, so its address is compiled in and a build reaches it with no setup.
# FLYWHEEL_BULLETIN_URL still wins, for anyone running their own deployment.
LANES: dict[str, Lane] = {
    "gather": Lane(
        "gather", "gather-engine", "gather", ("mcp",), "pip", "1.8.2",
        "research intake + provenance receipts (verified-data flywheel intake)",
        "perception", source_repo="public/gather", py_module="gather.cli"),
    "crucible": Lane(
        "crucible", "crucible-bench", "crucible", ("mcp",), "pip", "1.2.0",
        "falsifiable verification + re-check (register -> steelman -> measure -> witness)",
        "verification", source_repo="public/crucible", py_module="crucible.cli"),
    "chorus": Lane(
        "chorus", "chorus-discourse", "chorus", ("mcp",), "pip", "0.3.1",
        "re-derivable discourse digest (themes, contested aspects, dissent, receipt)",
        "synthesis", source_repo="public/chorus", py_module="chorus.cli"),
    "articulate": Lane(
        # articulate-mcp, not `python -m articulate.mcp_server`. The FastMCP
        # entry imports fastmcp from the [mcp] extra, so a plain
        # `pip install articulate-writing` left it raising ModuleNotFoundError
        # at launch through 0.3.0. The extra cannot go in install_name either:
        # installed_version() passes that string to importlib.metadata.version,
        # which does not accept an extras marker. 0.4.0 adds
        # articulate.local_mcp, stdlib-only and serving the same tools plus
        # status and doctor, so the lane installs and launches from one clean
        # name. Same shape as accountable-surface below, same reason.
        "articulate", "articulate-writing", "articulate-mcp", (),
        "pip", "0.4.0",
        "writing-quality + AI-tell detector and editor with content-free audit receipts (stdlib-only MCP server; the FastMCP surface stays under the [mcp] extra)",
        "authoring", source_repo="articulate", py_module="articulate.local_mcp"),
    "index": Lane(
        "index", "index-graph", "index", ("mcp",), "pip", "2.13.0",
        "workspace map + symbol graph + verified wiki (the catalog lane)",
        "structure", source_repo="public/index", py_module="index_graph"),
    "forum": Lane(
        "forum", "forum-engine", "forum", ("mcp",), "pip", "1.14.0",
        "witnessed causal ledger + model-agnostic routing",
        "orchestration", source_repo="public/forum", py_module="forum.cli"),
    "learn": Lane(
        "learn", "@harperz9/learn", "node", ("src/mcp.mjs",), "npm", "1.6.0",
        "accountable learning forge (spaced repetition + retrieval practice)",
        "learning", source_repo="public/learn"),
    "telos": Lane(
        "telos", "project-telos-mcp", "node", ("demo/telos-mcp.mjs",), "npm", "0.2.0",
        "the reconciliation lane: five-tool workflow + creative engine + doctors",
        "reconciliation", source_repo="public/telos",
        package_disabled_reason="No published npm distribution is available. Use a Telos source checkout."),
    "local-model": Lane(
        "local-model", "", "python", ("-m", "harness.local_mcp"), "bundled", "0.1.0",
        "the trained 14B proposer + verified-inference harness (the engine lane)",
        "propose-verify"),
    "writing": Lane(
        "writing", "", "python", ("-m", "harness.writing_mcp"), "bundled", "0.1.0",
        "private author workspace: scoped revisions, exact approval, and export receipts",
        "authoring"),
    "relay": Lane(
        "relay", "flywheel-relay", "relay", ("--mcp",), "pip", "0.2.5",
        "accountable coding agent on any model endpoint (local-first, witnessed runs)",
        "execution", source_repo="public/relay", py_module="relay.local_mcp"),
    "plexus": Lane(
        "plexus", "plexus-mesh", "plexus", ("mcp",), "pip", "0.2.2",
        "capability discovery + auto-wiring of the tool mesh (the layer above a flat tool list)",
        "wiring", source_repo="public/plexus", py_module="plexus.cli"),
    "mneme": Lane(
        "mneme", "flywheel-mneme", "mneme", ("mcp",), "pip", "0.4.2",
        "accountable memory: recall with re-derivable ranking receipts + drift verdicts",
        "memory", source_repo="public/mneme", py_module="mneme.cli"),
    "calibrate-pro": Lane(
        "calibrate-pro", "calibrate-pro", "calibrate-pro", ("mcp",), "pip", "2.0.0",
        "evidence-labeled display calibration: color-target and characterized-panel "
        "catalog + readiness doctor (read-only over MCP; actuation stays GUI-gated)",
        "calibration", source_repo="public/calibrate-pro", py_module="calibrate_pro.main"),
    "canon": Lane(
        "canon", "flywheel-canon", "canon", ("mcp",), "pip", "0.2.0",
        "provider-neutral memory bank + personality container: one envelope, "
        "deterministic render into a marked region of the instruction files "
        "(read-only over MCP; reconcile rewrites files, so it stays a library call)",
        "continuity", source_repo="public/canon", py_module="canon.cli"),
    "bulletin": Lane(
        "bulletin", "", "", (), "http", "0.2.0",
        "the open board: a workstation or another agent reaches it over the web, "
        "registers an ed25519 identity, and reads what other agents left behind",
        "correspondence", url="https://bulletin.zaindharper.workers.dev/mcp"),
    "accountable-surface": Lane(
        # accountable-surface-mcp, not accountable-surface-server. The server
        # entry imports mcp.server.fastmcp, which lives in the [server] extra, so
        # a plain `pip install accountable-surface` leaves it raising
        # ModuleNotFoundError at launch. The extra cannot go in install_name
        # either: installed_version() passes that string to
        # importlib.metadata.version, which does not accept an extras marker.
        # accountable_surface.interop_mcp is stdlib-only and serves the same
        # protocol, so the lane installs and launches from one clean name.
        "accountable-surface", "accountable-surface", "accountable-surface-mcp", (),
        "pip", "0.3.1",
        "live accountability seam: witnessed perception + operator-grant pre-execution "
        "gate + self-verifying effectors + tamper-evident journal (actuates, so T2)",
        "actuation", source_repo="public/accountable-surface",
        py_module="accountable_surface.interop_mcp",
        extra_source_repos=("public/coherence-membrane", "public/proof-surface")),
}
