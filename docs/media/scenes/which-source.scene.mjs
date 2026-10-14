// "Which source decides": Flywheel's output check on the Form 1040 example.
// Rendered by raw-native's media engine (docs/media/media.json). Every number on
// screen is read from this checkout when the video is rendered: the two answers,
// the checker's rule in tax_table.py, and what the output check prints, with its
// exit codes. The scene draws the rate schedule and the tax table from that rule,
// and checks its own table against the checker's answer before it draws anything.
import { rect, contour } from "@raw-native/motion/path.mjs";
import { text, fmt } from "@raw-native/motion/text.mjs";
import { span, window, ease, lerp, lerpLog } from "@raw-native/motion/timeline.mjs";
import { sayTimeline } from "@raw-native/motion/narration.mjs";

const C = { ink: "#ece5d6", ink2: "#b8b0a0", dim: "#958e80", frame: "#2a2830", ok: "#63d4ce", hot: "#e29472", unv: "#b3b1e6" };
const VERDICT = { PASS: C.ok, FAIL: C.hot, UNVERIFIABLE: C.unv };
const PLOT = { x0: 220, x1: 1700, y0: 860, y1: 220 };   // screen box: left, right, bottom, top
const money = (v) => (Number.isInteger(v) ? fmt(v) : fmt(v, 2));

export default {
  title: "Which source decides",
  burnsCaptions: true,
  duration: 60,
  fps: 30,
  chapters: [],
  async load(ctx) {
    const facts = await ctx.json("../facts.json"), F = facts.facts, v = (k) => F[k].value;
    const timing = await ctx.json("../timing.json").catch(() => null);
    const income = Number(v("income")), filed = Number(v("filed_tax")), tableTax = Number(v("table_tax"));
    const row = Number(v("row_width")), b1 = Number(v("bracket1")), r1 = Number(v("rate1")), b2 = Number(v("bracket2")), r2 = Number(v("rate2"));
    const schedule = (x) => Math.min(x, b1) * r1 + Math.max(0, Math.min(x, b2) - b1) * r2;
    const midpointOf = (x) => Math.floor(x / row) * row + row / 2;
    const table = (x) => Math.round(schedule(midpointOf(x)) + 1e-9);
    const mid = midpointOf(income);
    // The scene's rule must give what the checker program gives, or the picture would mislead.
    const agrees = table(income) === Number(v("checker_value")) && table(income) === tableTax && Math.abs(schedule(income) - filed) < 0.005;
    const pct = (r) => fmt(Math.round(r * 100));
    const lines = [
      `Flywheel ${v("version")} checks a value against the source that decides it.`,
      `A published demo filed a Form 1040 with a taxable income of $${fmt(income)} and a tax of $${money(filed)}.`,
      `The rate schedule gives that figure: ${pct(r1)} percent up to $${fmt(b1)}, then ${pct(r2)} percent on the rest.`,
      `But the form requires the tax table. Its rows are $${row} wide, and it charges tax on the middle of the row, $${fmt(mid)}.`,
      `That gives $${money(tableTax)}. Both numbers are arithmetically correct.`,
      `So the check does not reread the arithmetic. It asks the source the contract names, and the filed answer reads ${v("filed_verdict")}.`,
      `The answer from the table reads ${v("table_verdict")}. With nothing allowed to decide, the same answer reads ${v("unchecked_verdict")}.`,
      "A check nobody could run never reads as a check that passed.",
    ];
    const tl = sayTimeline(lines, { timing });
    this.duration = tl.duration;
    this.captions = () => tl.vtt();
    this.chapters = [{ t: 0, title: "The value" }, { t: tl.at(2), title: "Two sources" }, { t: tl.at(5), title: "The check" }];
    const A = { F, tl, income, filed, tableTax, row, b2, mid, schedule, table, agrees, atlas: await ctx.json("atlas.json") };
    frameOut.atlas = A.atlas;
    const T = (s, size, x, y, anchor = "center") => text(s, { atlas: A.atlas, size, x, y, anchor }).shape;
    A.L = {
      title: T("Which source decides", 72, 960, 500), sub: T(`Flywheel ${v("version")}, at commit ${(facts.commit || "").slice(0, 7)}`, 28, 960, 560),
      xAxis: T("taxable income", 24, PLOT.x1, PLOT.y0 + 46, "right"), yAxis: T("tax", 24, PLOT.x0 - 16, PLOT.y1 - 16, "right"),
      scheduleL: T("rate schedule", 26, 0, 0, "left"), tableL: T("tax table", 26, 0, 0, "left"),
      authority: T(`the contract names: ${v("authority")}`, 28, 960, 300),
      cards: [["as filed", "filed"], ["from the table", "table"], ["nothing allowed to decide", "unchecked"]].map(([name, k], i) => ({
        name: T(name, 30, 380 + i * 580, 470), verdict: T(String(v(`${k}_verdict`)), 52, 380 + i * 580, 560),
        exit: T(`exit ${v(`${k}_exit`)}`, 30, 380 + i * 580, 620), color: VERDICT[v(`${k}_verdict`)] || C.ink2,
      })),
      mismatch: T("the scene's table rule disagrees with the checker: numbers not drawn", 30, 960, 540),
    };
    return A;
  },
  frame(t, ctx) {
    const A = ctx.assets, tl = A.tl, items = [];
    const put = (shape, color, o) => { if (o > 0) items.push({ shape, fill: color, opacity: o, screen: true }); };
    const line = (pts, color, w, o) => { if (o > 0 && pts.length >= 4) items.push({ shape: [contour(pts, false)], stroke: color, width: w, opacity: o, screen: true }); };
    put(A.L.title, C.ink, window(t, 0.2, tl.at(1) - 0.2, 0.8, 0.8));
    put(A.L.sub, C.ink2, window(t, 0.5, tl.at(1) - 0.2, 0.8, 0.8));
    if (!A.agrees) { put(A.L.mismatch, C.hot, window(t, tl.at(1), tl.duration, 0.5, 0.5)); return frameOut(items, t, tl, put); }
    // The plot: the view zooms from the whole first two brackets into one row of the table.
    const plotA = window(t, tl.at(1) - 0.3, tl.at(5) + 0.4, 0.8, 0.8);
    if (plotA > 0) {
      const z = span(t, tl.at(3) - 0.2, tl.at(3) + 3.2, ease.inOut);
      const xw = lerpLog(A.b2, A.row * 5, z), xc = lerp(A.b2 / 2, A.mid, z);
      const x0 = xc - xw / 2, x1 = xc + xw / 2;
      // The tax axis follows the income axis, so the schedule always crosses the box corner to corner.
      const s0 = A.schedule(Math.max(0, x0)), s1 = A.schedule(x1), pad = (s1 - s0) * 0.08;
      const yy0 = s0 - pad, yy1 = s1 + pad;
      const X = (x) => PLOT.x0 + ((x - x0) / (x1 - x0)) * (PLOT.x1 - PLOT.x0);
      // Values outside the box are held to its edge, so nothing draws past the axes.
      const Y = (y) => Math.min(PLOT.y0, Math.max(PLOT.y1, PLOT.y0 + ((y - yy0) / (yy1 - yy0)) * (PLOT.y1 - PLOT.y0)));
      line([PLOT.x0, PLOT.y0, PLOT.x1, PLOT.y0], C.dim, 1.5, plotA);
      line([PLOT.x0, PLOT.y0, PLOT.x0, PLOT.y1], C.dim, 1.5, plotA);
      put(A.L.xAxis, C.dim, plotA); put(A.L.yAxis, C.dim, plotA);
      // Ticks on the income axis, in round numbers for the current span.
      // At most about five ticks: steps of 1, 2 or 5 times a power of ten.
      const raw = xw / 5, p10 = Math.pow(10, Math.floor(Math.log10(raw)));
      const step = [1, 2, 5, 10].map((m) => m * p10).find((s) => s >= raw);
      for (let x = Math.ceil(x0 / step) * step; x <= x1; x += step) {
        const sx = X(x);
        line([sx, PLOT.y0, sx, PLOT.y0 + 8], C.dim, 1.2, plotA);
        put(text(`$${fmt(x)}`, { atlas: A.atlas, size: 20, x: sx, y: PLOT.y0 + 30, anchor: "center" }).shape, C.dim, plotA * 0.9);
      }
      // The rate schedule: a straight line in each bracket.
      const sched = [];
      for (let i = 0; i <= 200; i++) { const x = x0 + (xw * i) / 200; sched.push(X(x), Y(A.schedule(x))); }
      const draw = span(t, tl.at(2) - 0.2, tl.at(2) + 2.2, ease.inOut);
      line(sched.slice(0, Math.max(4, Math.floor(sched.length * draw / 2) * 2)), C.ink, 2.5, plotA * (draw > 0 ? 1 : 0));
      // The tax table: flat across each row, at the tax on the row's midpoint.
      const tab = span(t, tl.at(3) + 1.0, tl.at(3) + 2.6);
      if (tab > 0) {
        const pts = [], r0 = Math.floor(x0 / A.row) * A.row;
        const rows = Math.min(4000, Math.ceil((x1 - r0) / A.row));
        for (let k = 0; k < rows; k++) { const a = r0 + k * A.row, ty = Y(A.table(a)); pts.push(X(a), ty, X(a + A.row), ty); }
        line(pts, C.ok, 2.5, plotA * tab);
        put(A.L.tableL, C.ok, 0);
      }
      // The filed answer on the schedule, and the row and midpoint the table uses.
      const dot = (x, y, color, o) => { if (o > 0) items.push({ shape: rect(X(x) - 7, Y(y) - 7, 14, 14, 7), fill: color, opacity: o, screen: true }); };
      dot(A.income, A.filed, C.hot, plotA * span(t, tl.at(1) + 1.5, tl.at(1) + 2.3));
      const rowA = plotA * span(t, tl.at(3) + 2.0, tl.at(3) + 3.0);
      if (rowA > 0) {
        const ra = Math.floor(A.income / A.row) * A.row;
        items.push({ shape: rect(X(ra), PLOT.y1, X(ra + A.row) - X(ra), PLOT.y0 - PLOT.y1), fill: C.frame, opacity: rowA * 0.6, screen: true });
        line([X(A.mid), PLOT.y0, X(A.mid), Y(A.tableTax)], C.ok, 1.5, rowA);
        put(text(`midpoint $${fmt(A.mid)}`, { atlas: A.atlas, size: 24, x: X(A.mid) + 12, y: PLOT.y0 - 20 }).shape, C.ok, rowA);
      }
      const val = plotA * span(t, tl.at(4), tl.at(4) + 0.8);
      dot(A.mid, A.tableTax, C.ok, val);
      put(text(`$${money(A.tableTax)}  the tax table`, { atlas: A.atlas, size: 30, x: X(A.mid) + 22, y: Y(A.tableTax) - 14 }).shape, C.ok, val);
      put(text(`$${money(A.filed)}  the rate schedule`, { atlas: A.atlas, size: 30, x: X(A.income) + 22, y: Y(A.filed) + 34 }).shape, C.hot, val);
    }
    // The check: the authority the contract names, then three runs and their verdicts.
    put(A.L.authority, C.ink, window(t, tl.at(5) + 0.4, tl.duration, 0.6, 1.0));
    A.L.cards.forEach((c, i) => {
      const at = i === 0 ? tl.at(5) + 1.5 : tl.at(6) + (i - 1) * 2.4;
      const o = window(t, at, tl.duration, 0.5, 1.0);
      if (o <= 0) return;
      items.push({ shape: rect(380 + i * 580 - 250, 420, 500, 240, 8), stroke: c.color, width: 2, opacity: o, screen: true });
      put(c.name, C.ink2, o); put(c.verdict, c.color, o); put(c.exit, C.ink2, o);
    });
    return frameOut(items, t, tl, put);
  },
};

function frameOut(items, t, tl, put) {
  for (const c of tl.cues) {
    const o = window(t, c.start, c.end, 0.3, 0.3);
    if (o > 0) put(text(c.text, { atlas: frameOut.atlas, size: 32, x: 960, y: 1030, anchor: "center" }).shape, "#ece5d6", o);
  }
  return { background: [0.024, 0.024, 0.031], camera: { x: 960, y: 540, zoom: 1 }, items, post: { bloom: 0.2, threshold: 0.9, vignette: 0.25, grain: 0.006 } };
}
