// Control fixture: a mod that passes every tool call on without asking the
// monitor. The hold check must fail against it, which shows the check can fail.
export function register(on) {
  on("tool.call", async ($, e, next) => next(e));
}
