// Audit fixture (never loaded): only denies. The word allow appears in a
// comment and a string, which must not count as an approval.
export function register(on) {
  on("tool.call", { tool: "Bash" }, async ($, e, next) => {
    // We never allow force pushes.
    if (/--force/.test(e.command)) return { deny: "Force pushes are not allowed here." };
    return next(e);
  });
  on("tool.check", { tool: "Bash" }, async ($, e, next) => {
    const decided = await next(e);
    if (e.input.command.includes("git push")) return { decision: "deny", reason: "no pushes" };
    return decided;
  });
}
