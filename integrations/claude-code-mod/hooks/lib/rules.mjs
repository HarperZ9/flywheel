// Risk pre-filter: which Bash, PowerShell, Edit, Write, MultiEdit and
// NotebookEdit calls are worth sending to the Flywheel pre-action monitor.
//
// This list never denies anything. A hit only routes the call to the monitor,
// which makes the hold-or-pass decision. A false positive costs one monitor
// run. A false negative skips the monitor, so the patterns err broad. Set the
// mod's `screen` option to `all` to send every matched tool call instead.
//
// Pure: no `$`, no I/O. Imported by the hooks module and by the tests.

export const SHELL_TOOLS = new Set(["Bash", "PowerShell"]);
export const FILE_TOOLS = new Set(["Edit", "Write", "MultiEdit", "NotebookEdit"]);

const SHELL_RULES = [
  { id: "shell/destructive", reason: "deletes files recursively or by force",
    re: /\brm\s+(-[a-zA-Z]*[rRf]|--recursive|--force)|\bRemove-Item\b[^|;&]*-(Recurse|Force)|\b(rmdir|rd)\s+\/s|\bdel\s+\/[sfq]|\bfind\b[^|;&]*-delete\b|\bshred\b|\bmkfs\b|\bdd\s+if=/i },
  { id: "shell/git-history", reason: "rewrites or discards git history or work",
    re: /\bgit\b[^|;&]*\b(reset\s+--hard|clean\s+-[a-zA-Z]*f|push\b[^|;&]*(--force|\s-f\b|\s\+\S)|checkout\s+(--\s+)?\.(\s|$)|restore\s+\.|branch\s+-D|filter-branch|filter-repo|update-ref\s+-d|reflog\s+expire|stash\s+(drop|clear))/i },
  { id: "shell/publish", reason: "publishes, pushes or merges outside the machine",
    re: /\b(npm|pnpm|yarn)\s+publish\b|\btwine\s+upload\b|\bgh\s+(release\s+create|pr\s+merge|repo\s+(create|delete|edit))\b|\bdocker\s+push\b|\bgit\b[^|;&]*\bpush\b|\bcargo\s+publish\b/i },
  { id: "shell/network", reason: "reaches the network from the shell",
    re: /\b(curl|wget|Invoke-WebRequest|Invoke-RestMethod|iwr|irm|scp|rsync|sftp|ftp|nc|ncat|ssh)\b/i },
  { id: "shell/opaque-exec", reason: "runs code the pre-filter cannot read",
    re: /\b(eval|iex|Invoke-Expression)\b|\b(bash|sh|zsh|cmd|pwsh|powershell)(\.exe)?\s+(-c|\/c|-Command|-EncodedCommand|-enc)\b|\b(python3?|py|node|ruby|perl)\s+-[ce]\b|base64\s+(-d|--decode)|\|\s*(ba)?sh\b/i },
  { id: "shell/privilege", reason: "changes privileges, permissions or system state",
    re: /\bsudo\b|\bdoas\b|\bchmod\s+(-R\s+)?[0-7]*7[0-7]*\b|\bchown\b|\bicacls\b|\breg(\.exe)?\s+(add|delete)\b|\bSet-ExecutionPolicy\b|\bschtasks\b|\bcrontab\b|\bsystemctl\b/i },
  { id: "shell/monitor-tamper", reason: "touches hook configuration or the monitor itself",
    re: /\.claude[\\/](settings|managed)|managed-settings\.json|[\\/.]flywheel[\\/]|\.flywheel\b|hook_cli|harness\.preaction|disableAllHooks|\b(kill|pkill|taskkill|Stop-Process)\b[^|;&]*(python|flywheel|claude)/i },
  { id: "shell/credential", reason: "touches a credential file or secret store",
    re: /[\\/]\.ssh[\\/]|\.aws[\\/]|\.netrc\b|\.git-credentials|\.npmrc\b|\.pypirc\b|\bid_(rsa|ed25519|ecdsa)\b|(^|[\s\\/'"])\.env(\.(?!example)[\w.-]+)?(\s|$|['"])|\bprintenv\b|\bGet-ChildItem\s+env:/i },
  { id: "shell/install", reason: "installs packages or runs install scripts",
    re: /\b(npm|pnpm|yarn)\s+(i|install|add)\b|\bnpx\s|\bpip3?\s+install\b|\buv\s+(pip\s+install|add)\b|\bgem\s+install\b|\bwinget\s+install\b|\bchoco\s+install\b/i },
  { id: "shell/database", reason: "runs a migration or a destructive database statement",
    re: /\bmigrate\b|\balembic\s+upgrade\b|\bdrop\s+(table|database|schema)\b|\btruncate\s+table\b/i },
];

const PATH_RULES = [
  { id: "file/config-tamper", reason: "writes hook, agent or CI configuration",
    re: /(^|[\\/])\.claude[\\/]|(^|[\\/])\.codex[\\/]|managed-settings\.json$|(^|[\\/])\.flywheel[\\/]|(^|[\\/])\.git[\\/]|(^|[\\/])\.github[\\/]workflows[\\/]|(^|[\\/])\.husky[\\/]|(^|[\\/])\.mcp\.json$|(^|[\\/])CLAUDE\.md$|(^|[\\/])AGENTS\.md$/i },
  { id: "file/credential", reason: "writes a credential or secret file",
    re: /(^|[\\/])\.env(\.(?!example$)[\w.-]+)?$|(^|[\\/])\.ssh[\\/]|(^|[\\/])\.aws[\\/]|\.netrc$|\.git-credentials$|\.npmrc$|\.pypirc$|\.(pem|key|p12|pfx)$|(^|[\\/])id_(rsa|ed25519|ecdsa)$/i },
  { id: "file/executable", reason: "writes a script, build or package manifest that later runs",
    re: /\.(sh|bash|ps1|psm1|bat|cmd)$|(^|[\\/])(package\.json|pyproject\.toml|setup\.py|Makefile|Dockerfile|\.npmrc)$/i },
];

/** Slash-normalized, lower-cased path for prefix checks. */
export function normPath(p) {
  return String(p ?? "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
}

/** True when `file` is absolute and outside `cwd`. A relative path is inside. */
export function outsideProject(file, cwd) {
  const f = normPath(file);
  const isAbs = f.startsWith("/") || /^[a-z]:\//.test(f);
  if (!isAbs || !cwd) return false;
  const root = normPath(cwd);
  return !(f === root || f.startsWith(root + "/"));
}

/** The path a file tool writes, from its arguments. */
export function targetPath(args) {
  return args?.file_path ?? args?.notebook_path ?? args?.path ?? "";
}

/**
 * Classifies one call. Returns `{ screen, hits }`: `screen` says whether the
 * monitor should see it, `hits` lists the rule ids and reasons that matched.
 */
export function classify(tool, args, cwd) {
  const hits = [];
  if (SHELL_TOOLS.has(tool)) {
    const command = String(args?.command ?? "");
    for (const r of SHELL_RULES) if (r.re.test(command)) hits.push({ id: r.id, reason: r.reason });
  } else if (FILE_TOOLS.has(tool)) {
    const file = targetPath(args);
    for (const r of PATH_RULES) if (r.re.test(file)) hits.push({ id: r.id, reason: r.reason });
    if (outsideProject(file, cwd)) hits.push({ id: "file/outside-project", reason: "writes outside the project folder" });
  }
  return { screen: hits.length > 0, hits };
}

export const RULE_IDS = [...SHELL_RULES, ...PATH_RULES].map((r) => r.id).concat("file/outside-project");
