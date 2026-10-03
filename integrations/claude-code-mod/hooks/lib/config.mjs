// The mod's options, from the manifest's userConfig (snake_case keys), with
// defaults filled and bad values replaced by the safe choice. Pure.

const SCREEN = new Set(["rules", "all"]);
const ON_UNAVAILABLE = new Set(["deny", "pass"]);
const STATUS_SITE = new Set(["band", "status", "off"]);

function pick(value, allowed, fallback) {
  return allowed.has(value) ? value : fallback;
}

function num(value, fallback, min, max) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
}

/** Normalized config. An unknown `on_unavailable` falls back to `deny`. */
export function normalizeConfig(options = {}) {
  const o = options ?? {};
  return {
    python: String(o.python || "python"),
    monitorSource: String(o.monitor_source || ""),
    monitorHome: String(o.monitor_home || ".flywheel/monitor"),
    monitorOwnerConfig: String(o.monitor_owner_config || ""),
    monitorDeadlineSeconds: num(o.monitor_deadline_seconds, 8, 1, 60),
    monitorTimeoutMs: num(o.monitor_timeout_ms, 15000, 2000, 600000),
    screen: pick(o.screen, SCREEN, "rules"),
    onUnavailable: pick(o.on_unavailable, ON_UNAVAILABLE, "deny"),
    statusSite: pick(o.status_site, STATUS_SITE, "band"),
    receiptsDir: String(o.receipts_dir || ".flywheel/mod-receipts"),
  };
}

/** The status line text. */
export function statusLine(counts, lastHash, cfg) {
  const parts = [`Flywheel  held ${counts.held}  passed ${counts.passed}`];
  if (counts.unavailable > 0) {
    parts.push(cfg.onUnavailable === "deny"
      ? `monitor unavailable ${counts.unavailable}x, failed closed`
      : `monitor unavailable ${counts.unavailable}x, FAILED OPEN`);
  }
  parts.push(lastHash ? `receipt ${lastHash.slice(0, 12)}` : "no receipt yet");
  return parts.join("  ·  ");
}

/** Joins a relative path onto the session folder; leaves an absolute one alone. */
export function resolveIn(cwd, p) {
  const s = String(p);
  if (/^([a-zA-Z]:[\\/]|[\\/])/.test(s) || !cwd) return s;
  return String(cwd).replace(/[\\/]+$/, "") + "/" + s;
}

/** A file-name-safe form of a session id. */
export function safeName(id) {
  return String(id ?? "").replace(/[^A-Za-z0-9_-]/g, "") || "session";
}
