/** Isolated local Worker fixture. Never loads deployment config or credentials. */
import { createRequire } from "node:module";
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { createHash } from "node:crypto";

export async function startWorker(sourceRoot, dependencyRoot, runtimeRoot) {
  const require = createRequire(join(dependencyRoot, "package.json"));
  const { Miniflare, convertV4MiniflareOptions } = require("miniflare");
  const { build } = require("esbuild");
  const bundle = await build({
    entryPoints: [join(sourceRoot, "src/worker.ts")], bundle: true,
    write: false, format: "esm", platform: "neutral", target: "es2022",
    external: ["node:*", "cloudflare:*"],
  });
  const script = bundle.outputFiles[0].text;
  const options = { host: "127.0.0.1", port: 0, cf: false,
    d1Persist: join(runtimeRoot, "d1"), kvPersist: join(runtimeRoot, "kv"),
    r2Persist: join(runtimeRoot, "r2"), durableObjectsPersist: join(runtimeRoot, "do"),
    workers: [{
    name: "bulletin-evaluation-local", modules: true, script,
    compatibilityDate: "2026-09-01", compatibilityFlags: ["nodejs_compat"],
    d1Databases: ["DB"], kvNamespaces: ["KEYS"], r2Buckets: ["MEDIA"],
    durableObjects: { FEED: { className: "FeedRoom", useSQLite: true } },
    bindings: { BULLETIN_POW_BITS: 8, BULLETIN_SIGNATURE_MAX_AGE: 300 },
  }] };
  const currentOptions = () => {
    if (!convertV4MiniflareOptions) return options;
    return { ...convertV4MiniflareOptions(options), telemetry: { enabled: false } };
  };
  const mf = new Miniflare(currentOptions());
  try {
    const base = String(await mf.ready).replace(/\/$/, "");
    if (!base.startsWith("http://127.0.0.1:")) throw new Error("not local");
    const db = await mf.getD1Database("DB");
    const names = (await readdir(join(sourceRoot, "schema"))).filter(n => /^\d+.*\.sql$/.test(n)).sort();
    for (const name of names) {
      const sql = await readFile(join(sourceRoot, "schema", name), "utf8");
      // D1 exec is line-based. SQL source migrations are fixed local fixtures.
      await db.exec(sql.replace(/--[^\n]*/g, "").replace(/\s+/g, " "));
    }
    const restart = async () => {
      options.workers[0].script += "\n// isolated observer restart control\n";
      await mf.setOptions(currentOptions());
    };
    return { mf, db, base, restart,
      bundleSha256: createHash("sha256").update(script).digest("hex") };
  } catch (error) {
    await mf.dispose();
    throw error;
  }
}
