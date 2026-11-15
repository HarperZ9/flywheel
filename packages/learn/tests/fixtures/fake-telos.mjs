// Offline stand-in for the telos render CLI. Ignores argv; prints a fixed render-result JSON.
// Used only by tests so telosRender is exercised without a real telos engine.
process.stdout.write(JSON.stringify({
  selected_profile: "canvas2d-receipt-renderer",
  fallback_chain: ["webgpu-splat-clustered", "webgl2-cluster-preview", "canvas2d-receipt-renderer"],
  scene_spec_hash: "sha256:" + "a".repeat(64),
  result_hash: "sha256:" + "b".repeat(64),
  verdict: "MATCH",
  evidence_refs: ["fixture"],
  artifactRef: "aid/fixture.svg",
}));
