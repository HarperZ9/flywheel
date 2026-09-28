# Rowan shader

`shaders/rowan.frag` draws the Rowan avatar volume live on the user's machine. It is a single-pass fragment shader run through Flutter's `FragmentProgram`. The presenter (`lib/widgets/rowan_presenter.dart`) loads it and falls back to a named drawn placeholder when the platform cannot compile a runtime shader.

## What it is, and what it is not

The shader is a rendered visual, not a claim about any model. It draws a twisted torus coil with a central aperture. It models no facial landmarks. The uniform names `uGaze` and `uMouth` are retained slot names from earlier revisions; they drive a light cloud position and the aperture opening, not any face. Motion defaults off, and the presenter stops its ticker when the avatar is static, hidden, or off-screen, so it costs nothing when nothing moves.

## Reviewed source hash

The reviewed source is pinned by SHA-256:

```
72cd6136bba787ef79080dc9bfdc39b533517e522342cb5fb8ce22247f8486cb
```

`test/rowan_shader_test.dart` recomputes the hash of `shaders/rowan.frag` and asserts it equals this value. The file is committed pure LF (`.gitattributes`: `desktop/shaders/*.frag text eol=lf`), so the hash is stable across platforms and checkouts. An edit to the shader that changes behavior without updating this document and the `expectedRowanShaderSha256` constant in the same commit fails the test, so this description cannot silently fall out of step with the code. When you change the shader on purpose, recompute the hash, update the constant, and update this document together.

## Uniform contract

The pose packs into eight float slots, as recorded in the shader header:

- `size[0:2]` resolution in pixels (`uResolution`)
- `time[2]` seconds since start (`uTime`)
- `motion[3]` motion gain 0..1 (`uMotion`); 0 freezes the clock
- `attention[4:6]` gaze offset, each axis clamped to -1..1 (`uGaze`)
- `yaw[6]` turn, clamped to -0.6..0.6 radians (`uYaw`)
- `opening[7]` aperture opening 0..1 (`uMouth`)

`RowanPose.uniforms` builds this list, and `test/rowan_shader_test.dart` checks that malformed values stay finite and bounded rather than reaching the shader as NaN or out-of-range.

## Geometry

`field()` is a signed distance field. The main body is a torus whose major radius varies with angle (`ringRadius`, base 0.475) and whose cross-section carries a thickness profile and a fine pleat. A separate rounded inner lip sits behind the main weave, so the aperture is a real occluding recess with parallax rather than a painted concentric stripe. The interior below r=0.18 is filled with a plain bound to avoid the polar singularity. `modelPoint()` applies the clamped yaw plus a small idle sway (only when motion is on) and a fixed tilt. `scene()` scales the field by `FIELD_SCALE` (0.42).

## Material and lighting

`material()` shades the surface with a key light and a fill light, a Fresnel rim, a broad soft specular, and a tight glint. `occlusion()` adds a four-probe ambient-occlusion heuristic; it is a shading approximation, not global illumination. The weave tone follows a satin model where ridges catch light and valleys keep depth. Closed toroidal cells (48 around the major angle, 16 around the minor) carry a seeded facet tone from a hash, so the surface reads as woven facets rather than a flat gradient. The inner lip (`part > 1.5`) uses a separate etched finish.

## Palette and finish

`finish()` tone-maps, then maps each pixel to the site's eight Outrun inks:

```
0.0392,0.0235,0.0784   0.1020,0.0471,0.1882   0.2510,0.0784,0.3765
0.7059,0.1255,0.4706   1.0,0.3059,0.6275      1.0,0.5412,0.3765
0.3137,0.8627,0.9412   0.9569,0.9255,1.0
```

This is a bounded single-pass approximation of the site's CPU OKLab palette search: it finds the two nearest inks by weighted RGB distance and picks between them with a 4x4 Bayer ordered dither. A phosphor grille darkens dim scanlines, with strength that grows with render size. The full CPU OKLab search and resampling are not reproduced here; this is the honest gap between the live avatar and the offline renderer.

## Cost budget

Per visible pixel, at most 64 raymarch steps, then 6 field evaluations for the surface normal (three central-difference axis pairs) and 4 for occlusion. The march stops early at a hit (distance < 0.0013) or at the far plane (travel > 2.83). The image is downsampled to a grid of `max(64, min(extent, 240))` cells before marching, and a circular mask discards pixels outside radius 0.92, so most of the frame never marches. Surface detail scales with the drawing extent (`mix(32, 108, ...)`), so a small avatar does less filament work than a large one.

## Fallback

When `FragmentProgram.fromAsset` fails (an unsupported platform, or a driver that rejects the program), the presenter shows a named drawn placeholder and no image. `test/rowan_shader_test.dart` covers this path: an unsupported shader keeps a named drawn fallback and produces no rendered image.

## Verification in this branch

- `test/rowan_shader_test.dart`: pose uniforms stay finite and bounded; `rowan.frag` matches the reviewed hash above; an unsupported shader keeps a named drawn fallback with no image.
- `test/rowan_presenter_test.dart`: the presenter starts static, turns with the keyboard, opts into motion, explains disabled controls while the renderer is pending, and fits a narrow viewport.

These tests run against the loaded shader source and the presenter widget. They do not claim the shader compiles on any specific GPU, driver, or device; that is checked at runtime with the drawn fallback as the honest floor.
