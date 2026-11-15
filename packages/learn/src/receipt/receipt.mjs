// Build the completion-proof receipt in two forms: a machine-readable JSON ledger and a
// human-readable Markdown summary. Both make explicit which steps were automated logistics
// vs. which graded steps the operator performed personally (credential provenance).
export function buildReceipt({ workflow, ledger, completion }) {
  const rows = ledger.entries();
  const steps = rows.map((r) => r.entry);
  const automatedLogistics = steps.filter((e) => e.kind === "step").length;
  const humanAssessments = steps.filter((e) => e.kind === "human-assessment").map((e) => ({ seq: e.seq, note: e.note, at: e.at }));
  const witnessedAutoSubmissions = steps.filter((e) => e.kind === "step" && e.submission === "witnessed-auto")
    .map((e) => ({ seq: e.seq, submittedStateDigest: e.submittedStateDigest, authorizedBy: e.authorizedBy ?? null }));
  // Steps flagged cost or irreversible that the engine performed, with the grant that allowed each.
  const authorizedCostSteps = steps.filter((e) => e.kind === "step" && e.costAuthorizedBy)
    .map((e) => ({ seq: e.seq, costAuthorizedBy: e.costAuthorizedBy }));
  const manualSubmissions = steps.filter((e) => e.kind === "human-gate" && e.stepKind === "submit").map((e) => ({ seq: e.seq }));
  const aidVisualizations = steps.filter((e) => e.kind === "aid-visualization")
    .map((e) => ({ seq: e.seq, concept: e.concept, selected_profile: e.selected_profile, result_hash: e.result_hash, verdict: e.verdict }));
  const verified = ledger.verify().ok;
  const certId = completion ? completion.certId : null;
  const json = { course: workflow.course, seal: workflow.seal, verified, automatedLogistics, humanAssessments, witnessedAutoSubmissions, manualSubmissions, authorizedCostSteps, aidVisualizations, certId, steps };
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const html = `<!doctype html><meta charset="utf-8"><title>Credential receipt — ${esc(workflow.course)}</title>
<style>body{font:15px/1.5 system-ui,sans-serif;max-width:44rem;margin:2rem auto;padding:0 1rem;color:#1a1a1a}
h1{font-size:1.4rem}.ok{color:#0a7d2c;font-weight:600}.no{color:#b00020;font-weight:600}
.k{color:#555}code{background:#f2f2f2;padding:1px 4px;border-radius:3px;font-size:.85em}
table{border-collapse:collapse;width:100%;margin:1rem 0}td,th{border:1px solid #ddd;padding:.35rem .5rem;text-align:left;font-size:.9em}
.note{color:#444;border-left:3px solid #0a7d2c;padding-left:.8rem;margin-top:1.2rem}</style>
<h1>Credential receipt — ${esc(workflow.course)}</h1>
<p class="k">Workflow seal: <code>${esc(workflow.seal)}</code></p>
<p>Ledger verified: <span class="${verified ? "ok" : "no"}">${verified ? "yes" : "NO"}</span>
 &nbsp;·&nbsp; Automated logistics: <b>${automatedLogistics}</b>
 &nbsp;·&nbsp; Human assessments: <b>${humanAssessments.length}</b>
 &nbsp;·&nbsp; Aid visualizations: <b>${aidVisualizations.length}</b>
 &nbsp;·&nbsp; Certificate: <b>${esc(certId ?? "(none)")}</b></p>
${humanAssessments.length ? `<table><tr><th>seq</th><th>graded step performed by the operator</th><th>at</th></tr>${humanAssessments.map((h) => `<tr><td>${esc(h.seq)}</td><td>${esc(h.note)}</td><td>${esc(h.at)}</td></tr>`).join("")}</table>` : ""}
<p class="note">The operator did the graded work for this credential. The engine ran the logistics and recorded every step. Run <code>learn verify</code> on this run to re-check the hash chain. Print this page to PDF for a shareable copy.</p>`;
  const markdown = [
    `# Credential receipt — ${workflow.course}`,
    ``,
    `- Workflow seal: \`${workflow.seal}\``,
    `- Ledger verified: **${verified ? "yes" : "NO"}**`,
    `- Automated logistics steps: **${automatedLogistics}**`,
    `- Human assessment steps (performed by the operator): **${humanAssessments.length}**`,
    ...humanAssessments.map((h) => `  - seq ${h.seq}: ${h.note} (${h.at})`),
    `- Certificate: ${certId ?? "(none captured)"}`,
    `- Aid visualizations (learning aids, kept apart from graded work): **${aidVisualizations.length}**`,
    ...aidVisualizations.map((v) => `  - ${v.concept ?? "(concept)"}: ${v.verdict} (${v.selected_profile ?? "n/a"})`),
    ``,
    `The operator did the graded work for this credential. The engine ran the logistics and recorded every step. Run \`learn verify\` on this run to re-check the chain.`,
  ].join("\n");
  return { json, markdown, html };
}
