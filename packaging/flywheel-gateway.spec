# PyInstaller spec for the frozen Flywheel gateway (onedir).
#
# Build (from the repo root):
#   python -m scripts.studio_runtime_packaging stage-pinned-payload
#     --sources packaging/studio-runtime-sources.json --work-root SOURCES
#     --manifest MANIFEST --payload-root PAYLOAD
#   $env:FLYWHEEL_STUDIO_BODY_RUNTIME_MANIFEST="PATH"
#   $env:FLYWHEEL_STUDIO_BODY_RUNTIME_PAYLOAD="PATH"
#   python -m PyInstaller packaging/flywheel-gateway.spec --noconfirm
# Output: dist/flywheel-gateway/ — the folder the desktop installer ships
# as its engine/ payload. Includes the relay submodule so `flywheel remote`
# and `flywheel relay` work from a frozen build.

import os
import sys
import json
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

# Discovery imports must not write cache files into the pinned staging payload.
# Child discovery processes inherit the same rule. Recheck the payload below.
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

repo = Path(SPECPATH).parent
relay_src = repo / "relay" / "src"
CANON_CONTEXT_HIDDEN_IMPORTS = [
    "canon", "canon.context_mcp", "canon.context_store",
    "canon.context_query", "canon.context_records", "canon.backends",
    "canon.backends.base", "canon.backends.sqlite", "canon.schema",
    "canon.validator", "canon.canonical_json",
]


def _python_lane_row(lane):
    manifest = repo / "packaging" / "python-lane-payloads.jsonl"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("lane") == lane:
            return row
    raise RuntimeError(f"python lane manifest missing {lane}")


def python_lane_source_root(repo_root, lane):
    row = _python_lane_row(lane)
    base_value = os.environ.get("FLYWHEEL_PYTHON_LANE_SOURCE_ROOT")
    if not base_value:
        raise RuntimeError(
            "FLYWHEEL_PYTHON_LANE_SOURCE_ROOT must point to staged Python lane sources")
    base = Path(base_value)
    return (base / f"{lane}-{row['owner_tag']}" / "src").resolve()


canon_src = python_lane_source_root(repo, "canon")
for import_root in (repo, relay_src, canon_src):
    value = str(import_root)
    while value in sys.path:
        sys.path.remove(value)
sys.path.insert(0, str(repo))
sys.path.insert(0, str(relay_src))
sys.path.insert(0, str(canon_src))
from scripts.check_bundled_lane_descriptors import check_lane_descriptor
from scripts.build_python_lane_payloads import (
    _hash_file as python_lane_hash_file,
    _verify_source_files as verify_python_lane_source_files,
)
from scripts.frozen_gateway_metadata import flywheel_verify_metadata_datas
from scripts.studio_runtime_packaging import pyinstaller_studio_runtime_inputs
from scripts.python_lane_freeze import (
    python_lane_freeze_datas, python_lane_freeze_inputs)
from scripts.frozen_payload_datas import (
    NODE_STAGE_ENV, check_pyz_slices, node_lane_stage_datas)
from scripts.frozen_license_datas import frozen_license_datas
from scripts.frozen_trace_imports import TRACE_CUSTODY_HIDDEN_IMPORTS
from scripts.frozen_adapter_imports import adapter_lane_hidden_imports
from scripts.frozen_tool_metadata import identity_data
from PyInstaller.config import CONF
import importlib.util


def canon_context_payload_datas(repo_root, source_root):
    row = _python_lane_row("canon")
    checkout = source_root.parent.resolve()
    manifest_sha256, _module_count, _total_bytes = verify_python_lane_source_files(
        row, checkout)
    if manifest_sha256 != row["component_descriptor"]["source"]["manifest_sha256"]:
        raise RuntimeError("staged Canon context source manifest mismatch")
    datas = [(str(repo_root / "packaging" / "python-lane-payloads.jsonl"), "packaging")]
    for notice in row["owner_project"]["license_files"]:
        path = (checkout / notice["path"]).resolve()
        if not path.is_relative_to(checkout):
            raise RuntimeError("Canon context license path escaped source root")
        if python_lane_hash_file(path) != notice["sha256"]:
            raise RuntimeError("Canon context license hash mismatch")
        datas.append((str(path), "python-lane-payloads/canon/licenses"))
    return datas

descriptor_check = check_lane_descriptor(repo, "relay")
if descriptor_check["verdict"] != "PASS":
    raise RuntimeError(
        "bundled Relay descriptor gate failed: "
        + ",".join(descriptor_check["blocking_codes"]))
relay_import = importlib.util.find_spec("relay.local_mcp")
relay_origin = Path(relay_import.origin).resolve() if relay_import and relay_import.origin else None
if relay_origin is None or not relay_origin.is_relative_to(relay_src.resolve()):
    raise RuntimeError("bundled Relay import shadowed outside relay/src")
mcp_import = importlib.util.find_spec("harness.local_mcp")
mcp_origin = Path(mcp_import.origin).resolve() if mcp_import and mcp_import.origin else None
if mcp_origin is None or not mcp_origin.is_relative_to((repo / "harness").resolve()):
    raise RuntimeError("frozen MCP import shadowed outside harness")
canon_context_import = importlib.util.find_spec("canon.context_mcp")
canon_context_origin = Path(canon_context_import.origin).resolve() if canon_context_import and canon_context_import.origin else None
if canon_context_origin is None or not canon_context_origin.is_relative_to(canon_src):
    raise RuntimeError("bundled Canon context import shadowed outside canon/src")
# Keep version/license metadata under Flywheel's stable owned metadata root.
distribution_data = flywheel_verify_metadata_datas(copy_metadata)
canon_context_datas = canon_context_payload_datas(repo, canon_src)
studio_runtime = pyinstaller_studio_runtime_inputs(repo)
# accountable_surface imports its siblings coherence_membrane and proof_surface,
# which the studio runtime payload stages. Put that payload on sys.path, after the
# lane sources the helper inserts at the front, so importing each lane to resolve
# its entrypoint finds those siblings without shadowing a lane's own source.
for _studio_root in studio_runtime.pathex:
    if _studio_root not in sys.path:
        sys.path.append(_studio_root)
# Every other manifest lane (relay is the submodule, Canon is wired above) bundles
# from its staged, hash-pinned source. The helper verifies each staged source
# manifest hash against its pin and that each entrypoint resolves from its own src
# before returning the analysis path entries and hidden imports.
lane_source_root = Path(os.environ["FLYWHEEL_PYTHON_LANE_SOURCE_ROOT"])
python_lane_pathex, python_lane_hidden, python_lane_receipts = (
    python_lane_freeze_inputs(repo, lane_source_root))
# Package data inside each pinned lane package (forum's default roster, for one)
# lands at its package-relative folder, where importlib.resources looks for it.
python_lane_datas = python_lane_freeze_datas(repo, lane_source_root)
# learn, telos and the Node runtime ship from the folder scripts/stage_node_lanes.py
# stages, under _internal/node-lanes. A build without that stage, or with a stage
# that lists a held lane (none is held today), fails here, not at run time.
node_lane_datas = node_lane_stage_datas(os.environ.get(NODE_STAGE_ENV))
# The Python runtime's license (PSF, with OpenSSL's Apache License 2.0) and each
# lane's pinned license ship under _internal/licenses; a missing text fails here.
license_datas = frozen_license_datas(repo, lane_source_root)

a = Analysis(
    [str(repo / "packaging" / "gateway_entry.py")],
    pathex=[str(canon_src), str(relay_src), str(repo), *python_lane_pathex,
            *studio_runtime.pathex],
    datas=[(str(repo / "site"), "site"),
           (str(repo / "harness/skill_resources/flywheel-evidence-task/SKILL.md"),
            "harness/skill_resources/flywheel-evidence-task"),
           (str(repo / "harness/skill_resources/flywheel-evidence-task/references/constraints.md"),
            "harness/skill_resources/flywheel-evidence-task/references"),
           *identity_data(repo, CONF['workpath']),
           (str(repo / "harness" / "gateway.py"), "harness"),
           (str(repo / "packaging" / "bundled-lanes" / "relay.json"),
            "packaging/bundled-lanes"),
           *canon_context_datas,
           *python_lane_datas,
           *node_lane_datas,
           *license_datas,
           *studio_runtime.datas,
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
        "harness.local_agent_cli", "harness.local_mcp",
        "harness.receipt_operations", *CANON_CONTEXT_HIDDEN_IMPORTS,
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
        *python_lane_hidden,
        *studio_runtime.hiddenimports,
        # Trace custody: the inventory resolves its adapters from dotted names,
        # which the analysis cannot follow (scripts/frozen_trace_imports.py).
        *TRACE_CUSTODY_HIDDEN_IMPORTS,
        # Adapter lanes (raw): the roster and install import the adapter by its
        # registry name, which the analysis cannot follow either.
        *adapter_lane_hidden_imports(),
    ],
    excludes=["tkinter", "matplotlib", "numpy", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)
# A reviewed slice (calibrate-pro) must freeze exactly its reviewed modules: an
# extra one reached code outside the review, a missing one breaks a slice tool.
check_pyz_slices(Path(pyz.tocfilename),
                 [json.loads(line) for line in (repo / "packaging" / "python-lane-payloads.jsonl")
                  .read_text(encoding="utf-8").splitlines() if line.strip()])

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

# A successful freeze must leave the source payload reusable byte-for-byte.
pyinstaller_studio_runtime_inputs(repo)
