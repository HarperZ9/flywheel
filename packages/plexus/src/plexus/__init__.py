"""plexus: capability discovery + auto-wiring for agent toolchains.

Point it at a set of tools that ship interop manifests and declarative discovery
wires producer to consumer into a pipeline, every edge tagged `declared` and
carrying the module its producer names. Discovery does not import or run cited
tools. Optional probe helpers in `plexus.registry` launch owned MCP servers only
when explicitly called. Zero runtime dependencies.
"""
from .agent_sdk import AuthorityContext, FlagshipAgentSDK, verify_workflow_trace
from .graph import to_dot, to_mermaid
from .manifest import Manifest, Port, validate
from .mesh import Edge, Mesh, discover
from .plan import plan_to, route
from .receipt import build_plan_receipt, verify_plan
from .registry import builtin_manifests, load_dir
from .run import pipeline_script
from .sdk_catalog import BUILTIN_SDK_TOOLS, AgentToolSpec, export_compact_catalog
from .sdk_colab import ColabJobRequest, emit_colab_job_spec

__version__ = "0.4.0"

__all__ = [
    "Manifest", "Port", "validate",
    "Mesh", "Edge", "discover",
    "plan_to", "route",
    "build_plan_receipt", "verify_plan",
    "to_mermaid", "to_dot", "pipeline_script",
    "builtin_manifests", "load_dir",
    "AgentToolSpec", "BUILTIN_SDK_TOOLS", "export_compact_catalog",
    "ColabJobRequest", "emit_colab_job_spec",
    "AuthorityContext", "FlagshipAgentSDK", "verify_workflow_trace",
    "__version__",
]
