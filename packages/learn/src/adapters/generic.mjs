// A config-driven adapter template. Real per-platform adapters are just a config of CSS selectors
// plus this behavior — NO graded logic anywhere (the engine halts at `assess` steps regardless).
// `captureCompletion` is the one method the runner invokes (on a `complete` step); the rest are
// helpers for workflow authoring.
import { registerAdapter } from "./types.mjs";

export function makeGenericAdapter(config = {}) {
  return {
    async enroll(driver) { if (config.enrollSelector) await driver.click(config.enrollSelector); return { enrolled: config.course ?? null }; },
    async modules() { return config.modules ?? []; },
    async advance(driver, moduleId) { if (config.nextSelector) await driver.click(config.nextSelector); return { advanced: moduleId }; },
    // Report WHERE graded content is, so the workflow author tags those steps `assess`. Never answers it.
    async locateAssessment() { return { selector: config.assessmentSelector ?? null, label: config.assessmentLabel ?? "assessment" }; },
    async captureCompletion(driver) {
      const snap = await driver.snapshot();
      const cap = await driver.capture(config.captureKind ?? "dom");
      return { certId: config.certId ?? ("cert:" + (snap.url || "unknown")), payload: cap.payload };
    },
  };
}

// A default generic adapter so `adapter: "generic"` resolves out of the box.
registerAdapter("generic", makeGenericAdapter({ certId: "cert:generic" }));
