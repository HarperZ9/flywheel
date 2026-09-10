/** Independent finite-state actor for instrument calibration, not a model. */
export async function nextAction(base, sourceId) {
  const response = await fetch(`${base}/v1/posts/${encodeURIComponent(sourceId)}`);
  if (!response.ok) throw new Error("source unavailable to scripted actor");
  const source = JSON.parse((await response.json()).post.body);
  const nextStates = { reported: "needs_review" };
  if (!Object.hasOwn(nextStates, source.state)) throw new Error("unsupported source state");
  // Never evaluates instructions, links or arbitrary extra fields in the body.
  return { task_id: source.task_id, state: nextStates[source.state] };
}
