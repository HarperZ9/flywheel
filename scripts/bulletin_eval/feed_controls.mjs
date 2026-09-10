/** Actual isolated FeedRoom calls: replay is volatile and limited, not an audit. */
import assert from "node:assert/strict";

async function readWindow(stub, lastId) {
  const headers = lastId ? { "last-event-id": lastId } : {};
  const response = await stub.fetch("http://feed/subscribe?room=scratch", { headers });
  assert.equal(response.status, 200);
  const reader = response.body.getReader();
  let text = "";
  const deadline = Date.now() + 500;
  try {
    while (Date.now() < deadline) {
      let timer;
      const next = await Promise.race([
        reader.read(),
        new Promise(done => { timer = setTimeout(() => done(null), deadline - Date.now()); }),
      ]);
      clearTimeout(timer);
      if (!next || next.done) break;
      text += new TextDecoder().decode(next.value);
    }
  } finally {
    await reader.cancel();
  }
  return [...text.matchAll(/^id: (.+)$/gm)].map(m => m[1]);
}

export async function feedControls(fixture) {
  const get = async () => {
    const ns = await fixture.mf.getDurableObjectNamespace("FEED");
    return ns.get(ns.idFromName("isolated-evaluation-replay"));
  };
  let stub = await get();
  for (let n = 0; n < 55; n++) {
    const response = await stub.fetch("http://feed/broadcast", {
      method: "POST", body: JSON.stringify({ id: `control-${n}`, type: "post", data: { room: "scratch" } }),
    });
    assert.equal(response.status, 204);
  }
  const unknownCursor = await readWindow(stub, "control-0");
  assert.equal(unknownCursor.length, 50);
  assert.equal(unknownCursor[0], "control-5");
  assert.equal(unknownCursor[49], "control-54");
  assert.deepEqual(await readWindow(stub, null), []);
  await fixture.restart();
  stub = await get();
  const afterRestart = await readWindow(stub, "control-0");
  assert.deepEqual(afterRestart, []);
  return {
    injected_events: 55, unknown_cursor_returned_events: 50,
    first_returned_event: "control-5", fresh_subscription_replayed_events: 0,
    after_worker_restart_replayed_events: afterRestart.length,
    observation_window_ms: 500,
    limit: "Isolated Durable Object calls, not signed public posts; no completeness guarantee from SSE.",
  };
}
