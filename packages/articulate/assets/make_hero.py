#!/usr/bin/env python
"""Generate the Articulate repository hero. Seeded and reproducible per the
design canon: a luminous aperture on a near-black ground, drawn from a field of
prose lines that bow around a verified core, with drift-marked spans, one
spectral flare, and a scanline grain veil. Verdict-only palette, two type
families. Output is 1280x640 so it doubles as the social preview."""
import math, random

W, H = 1280, 640
CX, CY = 848, 300           # aperture core, right of centre
R_VOID = 92                 # dark opening radius
R_FIELD = 250               # where the field deformation fades
SEED = 0x0A5C               # recorded on the mark
random.seed(SEED)

# verdict-only palette (sRGB from the site's oklch tokens)
VOID = "#0e0b18"
VOID2 = "#141024"
INK = "#f3eef8"
INK2 = "#c9c0d6"
FAINT = "#8c8296"
LIME = "#a8e832"            # verified
EMBER = "#e8843a"          # drift
MAGENTA = "#de3a8c"
CYAN = "#46cfe0"
IRIS = "#8a70e6"


def lerp(a, b, t):
    return a + (b - a) * t


def hex2rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def rgb2hex(r, g, b):
    return "#%02x%02x%02x" % (int(max(0, min(255, r))), int(max(0, min(255, g))), int(max(0, min(255, b))))


def mix(h1, h2, t):
    a, b = hex2rgb(h1), hex2rgb(h2)
    return rgb2hex(lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t))


def color_for(d):
    """closest-approach distance to the core -> verdict-graded stroke."""
    t = max(0.0, min(1.0, (d - R_VOID) / (R_FIELD - R_VOID)))
    if t < 0.5:
        return mix(LIME, INK2, t / 0.5)
    return mix(INK2, FAINT, (t - 0.5) / 0.5)


def opacity_for(d):
    t = max(0.0, min(1.0, (d - R_VOID) / (R_FIELD - R_VOID)))
    return round(lerp(0.95, 0.28, t), 3)


def deflect(x, y0, sign):
    """push a sample vertically so the line wraps the void, with a halo bulge."""
    dxc = x - CX
    y = y0
    if abs(dxc) < R_VOID:
        hv = math.sqrt(max(0.0, R_VOID * R_VOID - dxc * dxc))
        if abs(y0 - CY) < hv:
            return CY + sign * hv
    # halo: gentle outward bow for lines near the field
    dy = y0 - CY
    if abs(dxc) < R_FIELD and dy != 0:
        amp = 46.0
        push = amp * math.exp(-(dxc * dxc) / (2 * 118 * 118)) * math.exp(-(dy * dy) / (2 * 150 * 150))
        y = y0 + (1 if dy > 0 else -1) * push
    return y


lines = []
N = 46
y_top, y_bot = 58, 566
for i in range(N):
    y0 = lerp(y_top, y_bot, i / (N - 1))
    sign = 1 if y0 >= CY else -1
    if abs(y0 - CY) < 1:
        sign = 1 if i % 2 else -1
    pts, mind = [], 1e9
    x = 92.0
    jit = random.uniform(-1.2, 1.2)
    while x <= 1208:
        y = deflect(x, y0 + jit, sign)
        pts.append((round(x, 1), round(y, 1)))
        mind = min(mind, math.hypot(x - CX, y - CY))
        x += 15
    lines.append((pts, mind, y0))

# flagged spans: a few short ember ticks on seeded lines, away from the core
flag_idx = sorted(random.sample(range(6, N - 6), 3))
flags = []
for idx in flag_idx:
    pts = lines[idx][0]
    seg = random.choice([p for p in pts if p[0] < CX - R_FIELD or p[0] > CX + R_FIELD - 40])
    flags.append((seg[0], seg[1], random.choice([48, 62, 40])))

svg = []
svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="system-ui, \'Segoe UI\', Roboto, sans-serif">')
svg.append('<defs>')
svg.append(f'<radialGradient id="ground" cx="66%" cy="47%" r="75%"><stop offset="0%" stop-color="{VOID2}"/><stop offset="100%" stop-color="{VOID}"/></radialGradient>')
svg.append(f'<radialGradient id="core" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="{LIME}" stop-opacity="0.95"/><stop offset="55%" stop-color="{LIME}" stop-opacity="0.10"/><stop offset="100%" stop-color="{LIME}" stop-opacity="0"/></radialGradient>')
svg.append('<filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
svg.append('<filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter>')
svg.append('</defs>')

svg.append(f'<rect width="{W}" height="{H}" fill="url(#ground)"/>')
# core halo
svg.append(f'<circle cx="{CX}" cy="{CY}" r="{R_FIELD-40}" fill="url(#core)"/>')

# prose-line field
svg.append('<g fill="none" stroke-linecap="round">')
for pts, mind, y0 in lines:
    d = " ".join(f"{x},{y}" for x, y in pts)
    svg.append(f'<polyline points="{d}" stroke="{color_for(mind)}" stroke-opacity="{opacity_for(mind)}" stroke-width="1.5"/>')
svg.append('</g>')

# flagged-span ticks (drift)
svg.append('<g stroke-linecap="round">')
for fx, fy, fw in flags:
    svg.append(f'<line x1="{fx-fw/2}" y1="{fy}" x2="{fx+fw/2}" y2="{fy}" stroke="{EMBER}" stroke-width="3.4" stroke-opacity="0.92"/>')
svg.append('</g>')

# the aperture core: void, spectral flare (chromatic aberration), verified rings
svg.append(f'<circle cx="{CX}" cy="{CY}" r="{R_VOID+2}" fill="{VOID}"/>')
svg.append(f'<circle cx="{CX-2.4}" cy="{CY}" r="{R_VOID}" fill="none" stroke="{MAGENTA}" stroke-width="1.4" stroke-opacity="0.7"/>')
svg.append(f'<circle cx="{CX+2.4}" cy="{CY}" r="{R_VOID}" fill="none" stroke="{CYAN}" stroke-width="1.4" stroke-opacity="0.7"/>')
svg.append(f'<circle cx="{CX}" cy="{CY}" r="{R_VOID}" fill="none" stroke="{LIME}" stroke-width="2.4" filter="url(#glow)"/>')
svg.append(f'<circle cx="{CX}" cy="{CY}" r="{R_VOID-13}" fill="none" stroke="{LIME}" stroke-width="1" stroke-opacity="0.5"/>')
svg.append(f'<circle cx="{CX}" cy="{CY}" r="4.5" fill="{LIME}" filter="url(#glow)"/>')

# scanline veil + grain
svg.append('<g stroke="#000000" stroke-opacity="0.16" stroke-width="1">')
for y in range(0, H, 3):
    svg.append(f'<line x1="0" y1="{y}" x2="{W}" y2="{y}"/>')
svg.append('</g>')
svg.append(f'<rect width="{W}" height="{H}" filter="url(#grain)" opacity="0.05"/>')

# wordmark + tagline (grotesk) and the verdict metadata row (mono)
svg.append(f'<text x="96" y="452" fill="{INK}" font-size="82" font-weight="700" letter-spacing="-1.5">Articulate</text>')
svg.append(f'<text x="99" y="490" fill="{INK2}" font-size="20" font-weight="400" letter-spacing="0.3">A local writing-quality checker and editor. Not an authorship detector.</text>')
# mono metadata row with tiny verdict dots
mono = 'font-family="ui-monospace, \'DejaVu Sans Mono\', Menlo, Consolas, monospace"'
svg.append(f'<g {mono} font-size="14.5" letter-spacing="1.5">')
svg.append(f'<circle cx="101" cy="536" r="4" fill="{LIME}"/><text x="113" y="541" fill="{INK2}">MATCH</text>')
svg.append(f'<circle cx="199" cy="536" r="4" fill="{EMBER}"/><text x="211" y="541" fill="{INK2}">DRIFT</text>')
svg.append(f'<circle cx="291" cy="536" r="4" fill="{FAINT}"/><text x="303" y="541" fill="{INK2}">UNVERIFIABLE</text>')
svg.append(f'<text x="96" y="576" fill="{FAINT}" font-size="12.5" letter-spacing="1">re-derivable verdict   ·   standard-library core   ·   seed 0x{SEED:04X}</text>')
svg.append('</g>')

svg.append('</svg>')

open("assets/articulate-hero.svg", "w", encoding="utf-8").write("\n".join(svg))
print("wrote assets/articulate-hero.svg", len("\n".join(svg)), "bytes,", len(lines), "lines,", len(flags), "flags")
