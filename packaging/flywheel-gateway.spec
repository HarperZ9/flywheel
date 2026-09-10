# PyInstaller spec for the frozen Flywheel gateway (onedir).
#
# Build (from the repo root):
#   python -m PyInstaller packaging/flywheel-gateway.spec --noconfirm
# Output: dist/flywheel-gateway/ — the folder the desktop installer ships
# as its engine/ payload. Includes the relay submodule so `flywheel remote`
# and `flywheel relay` work from a frozen build.

import sys
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

repo = Path(SPECPATH).parent
relay_src = repo / "relay" / "src"
for import_root in (repo, relay_src):
    value = str(import_root)
    while value in sys.path:
        sys.path.remove(value)
sys.path.insert(0, str(repo))
sys.path.insert(0, str(relay_src))
from scripts.check_bundled_lane_descriptors import check_lane_descriptor
import importlib.util

descriptor_check = check_lane_descriptor(repo, "relay")
if descriptor_check["verdict"] != "PASS":
    raise RuntimeError(
        "bundled Relay descriptor gate failed: "
        + ",".join(descriptor_check["blocking_codes"]))
relay_import = importlib.util.find_spec("relay.local_mcp")
relay_origin = Path(relay_import.origin).resolve() if relay_import and relay_import.origin else None
if relay_origin is None or not relay_origin.is_relative_to(relay_src.resolve()):
    raise RuntimeError("bundled Relay import shadowed outside relay/src")
# Keep version/license metadata without pip's local installation URL.
distribution_data = [
    (str(path), str(Path(destination) / path.relative_to(source).parent))
    for source, destination in copy_metadata("flywheel-verify")
    for path in sorted(Path(source).rglob("*"))
    if path.is_file() and path.name != "direct_url.json"
]

a = Analysis(
    [str(repo / "packaging" / "gateway_entry.py")],
    pathex=[str(relay_src), str(repo)],
    datas=[(str(repo / "site"), "site"),
           (str(repo / "harness" / "gateway.py"), "harness"),
           (str(repo / "packaging" / "bundled-lanes" / "relay.json"),
            "packaging/bundled-lanes"),
           *distribution_data],
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
        "relay.remote_state", "harness.bundled_lane_admission",
        "harness.bundled_lane_expectations",
        # Desktop Bulletin identity setup is served through the frozen gateway.
        # The source package keeps cryptography optional; the Windows freeze
        # installs .[signing] and must carry the lazy route/import graph.
        "harness.bulletin_identity", "harness.bulletin_identity_contract",
        "harness.bulletin_identity_key", "harness.bulletin_identity_network",
        "harness.bulletin_identity_origin", "harness.bulletin_identity_store",
        "harness.bulletin_identity_route", "harness.bulletin_signed_transport",
        "harness.credential_handles", "harness.journey_lock",
        "harness.key_roster", "harness.keychain", "harness.keychain_route",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "cryptography.hazmat.primitives.serialization",
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
