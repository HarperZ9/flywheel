// Resume-automation tie-in — ingest an earned credential (from a learn receipt) into a
// resume/portfolio structure, carrying the provenance flag (was the ledger verified + was the
// graded work human-performed). Deterministic, zero-dep.
export function addCredential(resume, receiptJson, { at = null } = {}) {
  const r = { name: resume?.name ?? "", credentials: [...(resume?.credentials ?? [])] };
  const provenanceVerified = receiptJson.verified === true && (receiptJson.humanAssessments?.length ?? 0) > 0;
  r.credentials.push({
    course: receiptJson.course,
    certId: receiptJson.certId,
    provenanceVerified,           // ledger intact AND the operator personally did the graded work
    humanAssessments: receiptJson.humanAssessments?.length ?? 0,
    seal: receiptJson.seal,
    addedAt: at,
  });
  return r;
}

export function renderResumeMarkdown(resume) {
  const creds = resume?.credentials ?? [];
  return [
    `## Credentials & Certifications`,
    ``,
    ...creds.map((c) =>
      `- **${c.course}** — ${c.certId}` +
      (c.provenanceVerified ? " _(provenance-verified: graded work performed personally, ledger intact)_" : "")),
    creds.length ? "" : "_(none yet)_",
  ].join("\n");
}
