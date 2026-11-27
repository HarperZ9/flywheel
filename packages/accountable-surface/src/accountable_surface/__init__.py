"""The Accountable Surface -- a live seam where a model perceives and acts only
through accountability: witnessed perception, a pre-execution gate, and a
tamper-evident, durable memory, under human stewardship.

Mission: "Senses and sensibility are what lead to the new frontier. Machines
learning to hold themselves accountable."

The core (`surface`) is stdlib + coherence-membrane + proof-surface. The live
MCP server (`server`) additionally needs `mcp` (the `[server]` extra).
"""

from __future__ import annotations

from .api_effector import (
    GITHUB_ISSUE_COMMENTS,
    ApiCall,
    ApiEffector,
    ApiOperation,
    ApiService,
    FakeApiDriver,
)
from .action_receipt import (
    ActionReceiptReceptor,
    receipt_from_outcome,
    verify_receipts,
)
from .credentials import (
    MissingCredential,
    credential_fingerprint,
    has_credential,
    has_secret,
    require_secret,
    resolve_credential_handle,
)
from .keystore import (
    KEYSTORE_PREFIX,
    EncryptedFileKeystore,
    KeystoreError,
    KeystoreScopeError,
    KeystoreTamperError,
    KeystoreUnavailableError,
    MemoryKeystore,
    Win32CredentialKeystore,
    dpapi_protect,
    dpapi_unprotect,
    scoped_target_name,
    secret_fingerprint,
    validate_scoped_target,
)
from .oauth_broker import (
    DeviceFlowSession,
    OAuthBrokerError,
    OAuthTokenBroker,
    PKCEPair,
    build_authorization_url,
    compute_pkce_s256,
    generate_pkce_pair,
    redact_secrets,
)
from .request_signer import (
    AccountableRequestSigner,
    build_oauth1_authorization_header,
    compute_content_digest,
    sign_http_request_rfc9421,
    verify_http_request_rfc9421,
)
from .effector import FilesystemEffector, Plan, RefusedActuation, Verdict
from .native_control_effector import (
    SAFE_READ_VERBS,
    FakeNativeControlRunner,
    NativeControlListEffector,
    NativeControlRunner,
    NativeControlWriteEffector,
)
from .http_driver import HttpDriver, parse_html
from .os_effector import CommandEffector, SubprocessRunner
from .registry import EffectorRegistry, Exposed, load_effectors
from .reference import ArxivSource, FakeSource, Grounding, Reference, ReferenceCortex, parse_arxiv_atom
from .surface import (
    AccountableSurface,
    ActionOutcome,
    ActuationOutcome,
    GoalOutcome,
    JournalEntry,
    Step,
)
from .browser_effector import (
    BrowserAction,
    BrowserDriver,
    BrowserEffector,
    FakeBrowserDriver,
)
from .web_effector import FakePageDriver, WebAction, WebEffector
from .operator_backends import LocalSafeBackend, RollbackSnapshot, SimulatedWorkstationBackend
from .native_win32_backend import NativeWin32Backend, compile_win32_surface_dll, load_win32_surface_lib
from .operator_policy import AuthorityGate, AuthorityGrant, GateVerdict, OperatorAction, WorkstationObservation
from .operator_receipt import emit_operator_engine_receipt, verify_operator_engine_receipt
from .operator_workflows import run_workstation_routine, stage_application_packet, stage_outreach_draft
from .workstation_operator import OperatorSession, OperatorStepRecord, ReplayReport, verify_action_journal

__all__ = [
    "AccountableSurface",
    "ActionOutcome",
    "ActuationOutcome",
    "GoalOutcome",
    "Step",
    "JournalEntry",
    "FilesystemEffector",
    "Plan",
    "RefusedActuation",
    "Verdict",
    "WebEffector",
    "WebAction",
    "FakePageDriver",
    "BrowserEffector",
    "BrowserAction",
    "BrowserDriver",
    "FakeBrowserDriver",
    "HttpDriver",
    "parse_html",
    "CommandEffector",
    "SubprocessRunner",
    "ApiEffector",
    "ApiCall",
    "ApiOperation",
    "ApiService",
    "FakeApiDriver",
    "GITHUB_ISSUE_COMMENTS",
    "MissingCredential",
    "require_secret",
    "has_secret",
    "resolve_credential_handle",
    "has_credential",
    "credential_fingerprint",
    "KEYSTORE_PREFIX",
    "KeystoreError",
    "KeystoreScopeError",
    "KeystoreTamperError",
    "KeystoreUnavailableError",
    "MemoryKeystore",
    "EncryptedFileKeystore",
    "Win32CredentialKeystore",
    "dpapi_protect",
    "dpapi_unprotect",
    "scoped_target_name",
    "validate_scoped_target",
    "secret_fingerprint",
    "PKCEPair",
    "OAuthBrokerError",
    "compute_pkce_s256",
    "generate_pkce_pair",
    "build_authorization_url",
    "DeviceFlowSession",
    "OAuthTokenBroker",
    "redact_secrets",
    "AccountableRequestSigner",
    "compute_content_digest",
    "sign_http_request_rfc9421",
    "verify_http_request_rfc9421",
    "build_oauth1_authorization_header",
    "EffectorRegistry",
    "Exposed",
    "load_effectors",
    "ReferenceCortex",
    "Reference",
    "Grounding",
    "FakeSource",
    "ArxivSource",
    "parse_arxiv_atom",
    "NativeControlListEffector",
    "NativeControlWriteEffector",
    "NativeControlRunner",
    "FakeNativeControlRunner",
    "SAFE_READ_VERBS",
    "ActionReceiptReceptor",
    "receipt_from_outcome",
    "verify_receipts",
    "AuthorityGate",
    "AuthorityGrant",
    "GateVerdict",
    "OperatorAction",
    "WorkstationObservation",
    "RollbackSnapshot",
    "SimulatedWorkstationBackend",
    "LocalSafeBackend",
    "NativeWin32Backend",
    "load_win32_surface_lib",
    "compile_win32_surface_dll",
    "OperatorSession",
    "OperatorStepRecord",
    "ReplayReport",
    "verify_action_journal",
    "emit_operator_engine_receipt",
    "verify_operator_engine_receipt",
    "stage_outreach_draft",
    "stage_application_packet",
    "run_workstation_routine",
]
__version__ = "0.3.1"
