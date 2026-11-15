# Visual-Measurement Proof Packet `demo-visual`

**Verdict: MATCH** -- The sRGB swatch measured within tolerance of its color and luminance targets.

- **Scope:** One image artifact; sensorless display estimate; strictly read-only.
- **Read-only:** True (non-mutation boundary: no LUT / ICC / DDC change is applied or claimed)

## Artifact

- `srgb-swatch.png` (image, 1024x1024) -- `ba7816bf8f01...`

## Color assumptions

- space `sRGB` - transfer `sRGB` - white point `D65`

## Measurements

| Metric | Value | Target | Deviation | Tolerance | Verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| delta_e_2000_mean | 1.42 dE | 0.0 | 1.42 | 2.0 | MATCH |
| white_luminance | 118.0 cd/m2 | 120.0 | 2.0 | 5.0 | MATCH |

## Display caveats

- sensorless estimate, not sensor-measured (~3.7 dE typical on the i1Display3 path)
- no ICC/LUT/DDC applied; read-only packet

## Uncertainty

_none_

_Every verdict is re-derivable: the packet emits a crucible thesis + measurements so an independent checker recomputes it from the same evidence._