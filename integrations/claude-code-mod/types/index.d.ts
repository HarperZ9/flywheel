// Types for the flywheel-mod plugin. The mod keeps no $.state values and adds
// no noun to $, so plugin.json does not name this file as a contract. These
// types describe its options and the receipt line it writes, for tools that
// read the receipts.

/** The userConfig values Claude Code passes to register(on, options). */
export type FlywheelModOptions = {
  python?: string;
  monitor_source?: string;
  monitor_home?: string;
  monitor_owner_config?: string;
  monitor_timeout_ms?: number;
  monitor_deadline_seconds?: number;
  screen?: "rules" | "all";
  on_unavailable?: "deny" | "pass";
  status_site?: "band" | "status" | "off";
  receipts_dir?: string;
};

/** What the mod decided for one guarded tool call. */
export type CallDecision = "pass" | "pass-unscreened" | "held" | "unavailable-deny" | "unavailable-pass";

/** One guarded tool call inside a turn receipt. */
export type ReceiptCall = {
  tool_use_id: string;
  tool: string;
  /** SHA-256 of the canonical JSON of the tool's arguments; equals Flywheel's args_sha256. */
  input_sha256: string;
  screened: boolean;
  rule_hits: string[];
  decision: CallDecision;
  monitor: { verdict: "pass" | "held" | "unavailable"; hold_id: string | null; reason: string | null } | null;
  /**
   * What happened after the mod's decision. `error` covers a tool error and
   * a refusal by Claude Code's own permission check: core reports both to
   * tool.call hooks as an errored result. `denied-downstream` means a hook
   * after this mod answered `{ deny }`.
   */
  outcome: "pending" | "ran" | "error" | "denied-by-mod" | "denied-downstream";
  file?: { path: string; before_sha256: string | null; after_sha256: string | null };
};

/** One line of .flywheel/mod-receipts/<session>.jsonl. */
export type TurnReceipt = {
  schema: "flywheel.mod-turn-receipt/v1";
  session_id: string;
  turn_id: string;
  agent_id: string | null;
  reason: string;
  is_aborted: boolean;
  ended_at_ms: number | null;
  counts: { seen: number; screened: number; held: number; passed: number; unavailable: number };
  calls: ReceiptCall[];
  prev_hash: string | null;
  record_hash: string;
};
