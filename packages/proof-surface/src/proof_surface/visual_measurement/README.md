# Visual Truth Kit (`proof_surface.visual_measurement`)

> Make a visual output prove itself: artifact digest, declared color assumptions,
> measured metrics, honest display caveats, and a re-derivable verdict.

Wedge #2. A **read-only** visual/color/display measurement proof packet.

## One command

```bash
python -m proof_surface.visual_measurement \
  --input examples/visual_measurement/measurement.json \
  --claim "The sRGB swatch measured within tolerance." \
  --scope "One image; sensorless estimate; read-only." \
  --packet-id demo-visual --out demo-out
# emits: packet.json · report.md · crucible-thesis.json · crucible-measurements.json
```

The input JSON carries `artifact` (name/sha256/kind), `color` (space/transfer/white
point), `metrics` (`value` vs `target` within `tolerance`, produced by Build Color /
Calibrate Pro), and honest `display_caveats`. Each metric's deviation is `|value -
target|`; the verdict uses the shared crucible-faithful rule and re-derives through
real crucible.

## The non-mutation boundary is structural

`read_only` **must** be `true`. This v0 packet records and verifies measurements;
it never applies a LUT / ICC / DDC change and never claims hardware calibration it
did not perform. Metrics arrive as data, so the kit takes **zero** dependency on
Build Color, Calibrate Pro, or any display hardware — a third party can run it with
nothing but proof-surface installed. It inherits the family's forbidden-field and
authority-language guards (so it cannot call a display "CERTIFIED").
