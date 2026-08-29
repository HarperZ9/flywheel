# PyInstaller spec for the frozen Flywheel gateway (onedir).
#
# Build (from the repo root):
#   python -m PyInstaller packaging/flywheel-gateway.spec --noconfirm
# Output: dist/flywheel-gateway/ — the folder the desktop installer ships
# as its engine/ payload. Includes the relay submodule so `flywheel remote`
# and `flywheel relay` work from a frozen build.

from pathlib import Path

repo = Path(SPECPATH).parent
relay_src = repo / "relay" / "src"

a = Analysis(
    [str(repo / "packaging" / "gateway_entry.py")],
    pathex=[str(repo), str(relay_src)],
    datas=[(str(repo / "site"), "site")],
    hiddenimports=[
        "relay", "relay.remote_cli", "relay.remote_mcp", "relay.remote_oauth",
        "relay.oauth", "relay.local_agent_cli", "relay.local_agent",
        "relay.local_loop", "relay.local_mcp", "relay.local_tools",
        "relay.local_session", "relay.local_git", "relay.local_repomap",
        "relay.local_review_agent", "relay.endpoints", "relay.messages_api",
        "relay.async_runs", "relay.cert", "relay.integrity", "relay.contract",
        "relay.conventions", "relay.approvals", "relay.session_store",
        "relay.tools_prompt", "relay.udiff", "relay.edit_plan", "relay.watch",
        "relay.compaction", "relay.review", "relay.run_view",
        "relay.verified_bon", "relay.bisect", "relay.claim_grounding",
        "relay.injection_probe", "relay.intent_audit", "relay.hashline",
    ],
    excludes=["tkinter", "matplotlib", "numpy", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="flywheel-gateway",
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="flywheel-gateway",
)
