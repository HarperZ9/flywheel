// A stand-in for Claude Code's mods runtime, for running the mod under Node.
//
// It reproduces the documented semantics this mod relies on (code.claude.com
// mods reference and events pages, read 2026-10-02): on(event, matcher?, hook)
// returning a registration with .catch; matchers with a value, an array or a
// RegExp; a middleware chain ending in core; deeply frozen events; .catch runs
// when the hook throws before calling next, with next.error.kind; a hook that
// fails after next resolved leaves that result standing. It is not Claude
// Code: tests/engine.test.ts runs the same paths under `claude plugin test`
// against the real engine (2.1.286 or later).

export function deepFreeze(v) {
  if (v && typeof v === "object" && !Object.isFrozen(v)) {
    Object.freeze(v);
    for (const k of Object.keys(v)) deepFreeze(v[k]);
  }
  return v;
}

function matches(matcher, e) {
  if (!matcher) return true;
  return Object.entries(matcher).every(([k, want]) => {
    const got = e[k];
    if (want instanceof RegExp) return typeof got === "string" && want.test(got);
    if (Array.isArray(want)) return want.includes(got);
    return got === want;
  });
}

/**
 * Loads a module's register(on, options). `api` supplies the mods API calls
 * as "namespace.method" -> function(...args). Returns the engine.
 */
export function load(register, options = {}, api = {}) {
  const regs = [];
  const calls = [];   // every mods API call the mod made: { name, args }
  const returns = []; // every value a mod hook returned: { event, value, fromNext }
  const on = (event, a, b) => {
    const [matcher, hook] = typeof a === "function" ? [null, a] : [a, b];
    if (typeof event !== "string") throw new Error("event name must be a string literal");
    const reg = { event, matcher, hook, catchFn: null };
    regs.push(reg);
    return { catch(fn) { reg.catchFn = fn; return this; } };
  };
  register(on, options);

  const $ = new Proxy({}, {
    get(_, ns) {
      return new Proxy({}, {
        get(__, method) {
          const name = `${String(ns)}.${String(method)}`;
          return (...args) => {
            calls.push({ name, args });
            const impl = api[name];
            if (!impl) return Promise.reject(new Error(`no implementation for ${name}`));
            return impl(...args);
          };
        },
      });
    },
  });
  // ui.resolve and ui.invalidate are synchronous in the samples; model them so.
  const syncUi = {
    resolve: () => ({
      Box: (props) => ({ type: "Box", props }),
      Text: (props) => ({ type: "Text", props }),
    }),
    invalidate: (...args) => { calls.push({ name: "ui.invalidate", args }); },
  };
  const $mod = new Proxy($, {
    get(target, ns) {
      if (ns === "ui") {
        return new Proxy(target.ui, { get: (t, m) => syncUi[m] ?? t[m] });
      }
      return target[ns];
    },
  });

  async function fire(event, input, core) {
    const e0 = deepFreeze(structuredClone(input));
    const chain = regs.filter((r) => r.event === event && matches(r.matcher, e0));
    const run = async (i, e) => {
      if (i >= chain.length) return core(e);
      const reg = chain[i];
      let called = false;
      let nextResult;
      const next = async (e2) => {
        called = true;
        nextResult = await run(i + 1, e2);
        return nextResult;
      };
      next.signal = new AbortController().signal;
      try {
        const value = await reg.hook($mod, e, next);
        returns.push({ event, value, fromNext: called && value === nextResult });
        return value;
      } catch (error) {
        if (called) return nextResult; // failed after next resolved: that result stands
        if (reg.catchFn) {
          const handlerNext = async (e2) => run(i + 1, e2);
          handlerNext.error = { kind: "throw", message: String(error?.message ?? error) };
          handlerNext.called = false;
          const value = await reg.catchFn($mod, e, handlerNext);
          returns.push({ event, value, fromNext: false, fromCatch: true });
          return value;
        }
        return run(i + 1, e); // skipped
      }
    };
    return run(0, e0);
  }

  return { regs, calls, returns, fire, events: () => regs.map((r) => r.event) };
}

/** An in-memory file system for the $.fs calls. Paths compare slash-normalized. */
export function memoryFs(initial = {}) {
  const files = new Map(Object.entries(initial).map(([k, v]) => [norm(k), v]));
  function norm(p) { return String(p).replace(/\\/g, "/"); }
  return {
    files,
    api: {
      "fs.exists": async (p) => files.has(norm(p)),
      "fs.read": async (p) => {
        if (!files.has(norm(p))) throw new Error(`ENOENT ${p}`);
        return files.get(norm(p));
      },
      "fs.write": async (p, text) => { files.set(norm(p), text); },
    },
  };
}
