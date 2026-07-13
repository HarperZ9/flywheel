"""Self-contained offline HTML player for harness.demo-transcript/v1.

Everything is inline (CSS, JS, transcript data). No CDN, no fonts,
no src/href pointing at any network URL. Renders in any browser, offline.
"""

from __future__ import annotations

import html
import json

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ | demo player</title>
<style>
  :root {
    --bg: #0b0f14; --panel: #10161d; --edge: #1f2a35; --ink: #d7e0e8;
    --dim: #7b8a97; --green: #4ec9a4; --amber: #e0af68; --red: #e06c75;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font-family: "Cascadia Mono", "Consolas", "Courier New", monospace;
  }
  main { width: min(960px, calc(100vw - 24px)); margin: 0 auto; padding: 28px 0 60px; }
  header { display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: baseline; margin-bottom: 14px; }
  h1 { margin: 0; font-size: 1.15rem; letter-spacing: 0.04em; color: var(--green); }
  .meta { color: var(--dim); font-size: 0.78rem; }
  .terminal {
    background: var(--panel); border: 1px solid var(--edge); border-radius: 8px;
    min-height: 340px; padding: 16px 18px; white-space: pre-wrap; overflow-wrap: anywhere;
    font-size: 0.84rem; line-height: 1.5;
  }
  .titlebar { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--edge); }
  .dot.r { background: var(--red); } .dot.a { background: var(--amber); } .dot.g { background: var(--green); }
  .stepname { color: var(--dim); font-size: 0.78rem; margin-left: 8px; }
  .cmd { color: var(--amber); }
  .out { color: var(--ink); }
  .fail { color: var(--red); }
  .cursor { display: inline-block; width: 0.55em; height: 1em; background: var(--green);
            vertical-align: text-bottom; animation: blink 0.9s steps(1) infinite; }
  @keyframes blink { 50% { opacity: 0; } }
  .caption {
    margin-top: 12px; padding: 10px 14px; border-left: 3px solid var(--green);
    background: rgba(78, 201, 164, 0.07); color: var(--ink);
    font-size: 0.86rem; line-height: 1.55; min-height: 2.6em;
  }
  .controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 14px; }
  button {
    background: var(--panel); color: var(--ink); border: 1px solid var(--edge);
    border-radius: 6px; padding: 7px 14px; font: inherit; font-size: 0.8rem; cursor: pointer;
  }
  button:hover { border-color: var(--green); color: var(--green); }
  .status { color: var(--dim); font-size: 0.78rem; margin-left: auto; }
  .exit-ok { color: var(--green); } .exit-bad { color: var(--red); }
  progress { width: 100%; height: 4px; margin-top: 10px; accent-color: var(--green); }
</style>
</head>
<body>
<main>
  <header>
    <h1>__TITLE__</h1>
    <span class="meta">recorded __STAMP__</span>
    <span class="meta">__STEPS__ steps, total runtime __RUNTIME__</span>
    <span class="meta">receipt sha256:__RECEIPT__</span>
  </header>
  <div class="titlebar">
    <span class="dot r"></span><span class="dot a"></span><span class="dot g"></span>
    <span class="stepname" id="stepname"></span>
  </div>
  <div class="terminal" id="terminal"></div>
  <div class="caption" id="caption"></div>
  <progress id="bar" max="1" value="0"></progress>
  <div class="controls">
    <button id="play">Play</button>
    <button id="prev">Prev step</button>
    <button id="next">Next step</button>
    <button id="restart">Restart</button>
    <span class="status" id="status"></span>
  </div>
</main>
<script id="transcript-data" type="application/json">__DATA__</script>
<script>
(function () {
  "use strict";
  var transcript = JSON.parse(document.getElementById("transcript-data").textContent);
  var steps = transcript.steps || [];
  var term = document.getElementById("terminal");
  var caption = document.getElementById("caption");
  var stepname = document.getElementById("stepname");
  var statusEl = document.getElementById("status");
  var bar = document.getElementById("bar");
  var playBtn = document.getElementById("play");
  var CHARS_PER_TICK = 6, TICK_MS = 12, REVEAL_PAUSE_MS = 1400;
  var stepIndex = 0, charIndex = 0, playing = false, timer = null;

  function fullText(step) {
    return "$ " + step.command + "\\n" + (step.output || "") +
      "\\n[exit " + step.exit_code + " in " + step.duration_ms + " ms]";
  }
  function paint(partial) {
    var step = steps[stepIndex];
    if (!step) { return; }
    var text = fullText(step);
    var shown = partial ? text.slice(0, charIndex) : text;
    term.textContent = "";
    var cmdEnd = ("$ " + step.command).length;
    var cmdSpan = document.createElement("span");
    cmdSpan.className = "cmd";
    cmdSpan.textContent = shown.slice(0, cmdEnd);
    var outSpan = document.createElement("span");
    outSpan.className = step.exit_code === 0 ? "out" : "out fail";
    outSpan.textContent = shown.slice(cmdEnd);
    term.appendChild(cmdSpan);
    term.appendChild(outSpan);
    if (partial && shown.length < text.length) {
      var cur = document.createElement("span");
      cur.className = "cursor";
      term.appendChild(cur);
    }
    stepname.textContent = "step " + (stepIndex + 1) + "/" + steps.length + ": " + step.title;
    caption.textContent = step.narration;
    var exitCls = step.exit_code === 0 ? "exit-ok" : "exit-bad";
    statusEl.innerHTML = "";
    var tag = document.createElement("span");
    tag.className = exitCls;
    tag.textContent = "exit " + step.exit_code;
    statusEl.appendChild(document.createTextNode(step.mode + " | " + step.duration_ms + " ms | "));
    statusEl.appendChild(tag);
    bar.value = steps.length ? (stepIndex + (partial ? shown.length / Math.max(text.length, 1) : 1)) / steps.length : 0;
  }
  function tick() {
    var step = steps[stepIndex];
    if (!step) { stop(); return; }
    var total = fullText(step).length;
    if (charIndex < total) {
      charIndex = Math.min(total, charIndex + CHARS_PER_TICK);
      paint(true);
      timer = setTimeout(tick, TICK_MS);
    } else if (stepIndex < steps.length - 1) {
      timer = setTimeout(function () { stepIndex += 1; charIndex = 0; tick(); }, REVEAL_PAUSE_MS);
    } else {
      stop();
      paint(false);
    }
  }
  function stop() {
    playing = false;
    if (timer) { clearTimeout(timer); timer = null; }
    playBtn.textContent = "Play";
  }
  function start() {
    if (!steps.length) { return; }
    playing = true;
    playBtn.textContent = "Pause";
    tick();
  }
  playBtn.addEventListener("click", function () { playing ? stop() : start(); });
  document.getElementById("next").addEventListener("click", function () {
    stop(); stepIndex = Math.min(steps.length - 1, stepIndex + 1); charIndex = 0; paint(false);
  });
  document.getElementById("prev").addEventListener("click", function () {
    stop(); stepIndex = Math.max(0, stepIndex - 1); charIndex = 0; paint(false);
  });
  document.getElementById("restart").addEventListener("click", function () {
    stop(); stepIndex = 0; charIndex = 0; paint(true); start();
  });
  if (steps.length) { charIndex = 0; paint(true); }
})();
</script>
</body>
</html>
"""


def _format_runtime(total_ms: int) -> str:
    if total_ms < 1000:
        return f"{total_ms} ms"
    seconds = total_ms / 1000.0
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, rem = divmod(int(round(seconds)), 60)
    return f"{minutes} min {rem} s"


def render_player_html(transcript: dict) -> str:
    data = json.dumps(transcript, ensure_ascii=True).replace("</", "<\\/")
    return (
        _PAGE.replace("__DATA__", data)
        .replace("__TITLE__", html.escape(str(transcript.get("name", "demo"))))
        .replace("__STAMP__", html.escape(str(transcript.get("timestamp_utc", ""))))
        .replace("__STEPS__", str(transcript.get("step_count", 0)))
        .replace("__RUNTIME__", _format_runtime(int(transcript.get("total_duration_ms", 0))))
        .replace("__RECEIPT__", html.escape(str(transcript.get("receipt_sha256", ""))[:16]))
    )
