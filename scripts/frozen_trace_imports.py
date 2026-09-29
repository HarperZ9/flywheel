"""The trace custody modules the frozen gateway must carry, named literally.

The custody inventory resolves its export, delete and inventory adapters from
dotted strings (harness.trace_inventory.resolve), and PyInstaller cannot see an
import it only finds in a string. The trace routes, the startup probe, the
retention schedule and the bench sweep import the rest inside functions. The
spec adds every name here to its hidden imports, so `/api/traces/*` answers in
the Windows app the way it answers from a pip install.

The hook's own entry (harness.capture_hooks.__main__) is left out: it runs
under the owner's Python with `-m`, which the frozen gateway refuses.
tests/test_frozen_trace_imports.py fails when a trace module, a capture hook
module or an adapter the inventory names is missing from this list, and when
the list names a module that does not exist.
"""
from __future__ import annotations

TRACE_CUSTODY_HIDDEN_IMPORTS = (
    # the capture hook package: the gateway reads its spool and protect helpers
    "harness.capture_hooks",
    "harness.capture_hooks.client", "harness.capture_hooks.home",
    "harness.capture_hooks.listener_owner", "harness.capture_hooks.output",
    "harness.capture_hooks.protect", "harness.capture_hooks.protocol",
    "harness.capture_hooks.spool",
    # the engine side of the capture channel and custody removal
    "harness.gateway_bind", "harness.gateway_endpoint_file", "harness.gateway_request_sig",
    "harness.private_artifact_remove", "harness.private_artifact_remove_posix",
    "harness.private_artifact_remove_windows", "harness.store_tombstone",
    "harness.web_fetch_pinned", "harness.workspace_git_identity",
    # bench, capture and the chain log
    "harness.trace_bench", "harness.trace_bench_grant", "harness.trace_bench_replay",
    "harness.trace_bench_tasks",
    "harness.trace_capture_freeze", "harness.trace_capture_off",
    "harness.trace_capture_settings", "harness.trace_chain_log",
    # the command line
    "harness.trace_cli", "harness.trace_cli_capture", "harness.trace_cli_delete",
    "harness.trace_cli_export", "harness.trace_cli_import", "harness.trace_cli_presence",
    "harness.trace_cli_retention", "harness.trace_cli_text",
    # custody ledger, lock and deletion
    "harness.trace_custody_ledger", "harness.trace_custody_lock",
    "harness.trace_delete_adapters_enc", "harness.trace_delete_adapters_import",
    "harness.trace_delete_adapters_plain", "harness.trace_delete_apply",
    "harness.trace_delete_apply_plain", "harness.trace_delete_journal",
    "harness.trace_delete_plan",
    # doctor, durability and encryption
    "harness.trace_doctor", "harness.trace_doctor_checks", "harness.trace_doctor_mounts",
    "harness.trace_durable", "harness.trace_enc", "harness.trace_enc_aead",
    "harness.trace_enc_dpapi", "harness.trace_enc_floor", "harness.trace_enc_migrate",
    "harness.trace_enc_probe", "harness.trace_enc_write",
    # export and import
    "harness.trace_export", "harness.trace_export_dest", "harness.trace_export_manifest",
    "harness.trace_export_stores", "harness.trace_export_verify", "harness.trace_fs_attrs",
    "harness.trace_import_claude", "harness.trace_import_codex", "harness.trace_import_core",
    "harness.trace_import_exclusion", "harness.trace_import_items",
    "harness.trace_import_lines", "harness.trace_import_open_win",
    "harness.trace_import_read", "harness.trace_import_session",
    # inventory, keys and presence
    "harness.trace_inventory", "harness.trace_inventory_entries",
    "harness.trace_inventory_entries_ext", "harness.trace_inventory_scan",
    "harness.trace_keystore", "harness.trace_keystore_adapters",
    "harness.trace_meta_adapters", "harness.trace_presence",
    "harness.trace_presence_summary", "harness.trace_presence_verifiers",
    # redaction, residue, retention and routes
    "harness.trace_redact", "harness.trace_redact_finders", "harness.trace_redact_json",
    "harness.trace_redact_rules", "harness.trace_residual_scan", "harness.trace_retention",
    "harness.trace_retention_items", "harness.trace_retention_schedule",
    "harness.trace_routes", "harness.trace_routes_capture", "harness.trace_settings_guard",
    # stores, witness and compression
    "harness.trace_spool_adapters", "harness.trace_sqlite_scrub", "harness.trace_tombstones",
    "harness.trace_turn_receipt", "harness.trace_turn_store", "harness.trace_views_claude",
    "harness.trace_views_codex", "harness.trace_witness", "harness.trace_zstd",
)
