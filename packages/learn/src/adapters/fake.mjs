import { registerAdapter } from "./types.mjs";

registerAdapter("fake", {
  async enroll(course) { return { enrolled: course }; },
  async modules() { return ["m1", "m2"]; },
  async advance(m) { return { advanced: m }; },
  async locateAssessment() { return { selector: "#quiz", label: "quiz" }; },
  async captureCompletion() { return { certId: "cert-fake-1", payload: "certificate:fake:intro" }; },
});
