# Rowan's luminous companion

Rowan is the same assistant in chat, native tasks and presentation. The canonical
RowanAvatar draws an abstract luminous aperture through Flutter's FragmentProgram
and Paint.shader: rounded amber contours, a warm soft core and a restrained cool
rim. The shader contains analytical geometry and shading; no portrait bitmap,
image sampler, video or WebView supplies the character.

The visual recipe draws from the portfolio's
[seeded aperture](https://github.com/HarperZ9/HarperZ9.github.io/blob/dce83e300ef1a5045cb939acb3ae433352e0a460/system/generative-field.js#L2230)
and [Atelier layered light](https://github.com/HarperZ9/HarperZ9.github.io/blob/dce83e300ef1a5045cb939acb3ae433352e0a460/system/atelier.js#L1668).
This is a native interpretation, not a direct port of the site's 2D functions.

Chat uses static 32-pixel companions and a 64-pixel welcome character. Studio
contains the same renderer up to 320 pixels. Turn and Opening sliders support
keyboard input; pointer attention guides the core. Motion is explicitly opt-in.
Opening changes the aperture and does not represent speech or lip sync.

The black circular art ground is intentional in both app themes. Pixels outside
the circle remain transparent. The circle retains its aspect ratio on rectangular
canvases; the rest of the interface continues to use the selected app theme.

## Runtime boundary

The compiled FragmentProgram is cached. Each mounted avatar owns its own mutable
FragmentShader and disposes it on replacement or unmount. A failed program load
can be retried by a later mount; private driver errors are not displayed.

Static avatars have no running ticker. Opt-in motion updates the painter without
rebuilding the surrounding application. It pauses when reduced motion is enabled,
TickerMode is disabled, the app is not resumed, or the avatar is outside the
viewport. Scroll-position listeners and a paint observer outside the avatar's
repaint boundary restart eligible motion when the character becomes visible
again, including inside cached list children. There is no visibility polling timer.

Unsupported or failed shader loading produces a vector aperture with a soft core,
drawn with the selected theme's ink. Its
semantic label and tooltip name the fallback, and Studio explicitly reports that
the modeled renderer is unavailable. Pose and motion controls are disabled there.
While loading, the placeholder and Studio explain why controls are unavailable.
The fallback does not use a PNG or pretend to be a 3D model.

Receipt verdicts and model/provider choice remain separate UI controls. Neither
changes the character's identity or supplies a success-colored avatar.

## Shader contract

The shader is declared under flutter.shaders in pubspec.yaml. Eight-float ordering
is shared with RowanShaderPainter. GLSL keeps two historical names for slot
compatibility; Dart and user-facing controls use attention and opening:

| Float slots | GLSL uniform | Meaning |
| --- | --- | --- |
| 0, 1 | vec2 uResolution | Logical canvas width and height |
| 2 | float uTime | Elapsed active animation seconds |
| 3 | float uMotion | 0 for static, 1 for optional motion |
| 4, 5 | vec2 uGaze | Core attention offset, each -1 to 1 |
| 6 | float uYaw | Turn in radians, -0.6 to 0.6 |
| 7 | float uMouth | Aperture opening, 0 to 1 |

Nonfinite pose values become zero; finite values are clamped to this contract.
Output is premultiplied RGBA with transparent background. The integration uses
Paint.shader, not the Impeller-only ImageFilter.shader path.
The kernel uses at most 52 ray-march steps. Its reviewed source SHA-256 is
`3bed916a43cbba6bc657deadbfe606f7e915a5d17ebb0c1a8c46be507afa5672`.
Capture receipts record the actual source hash again on each run.

## Verification and capture

Run flutter analyze and the full flutter test suite in desktop. Focused tests
exercise actual shader loading, output coverage, pose differences, static-time
invariance, round bounds on rectangular targets, light/dark widget rendering, idle
behavior, reduced motion, app state, scrolling, keyboard controls and narrow
layouts. The fallback test injects a failed loader; rendering tests use the real
compiled FragmentProgram.

To retain native test-engine frames, set ROWAN_CAPTURE_DIR to a local output
directory and run:

```
flutter test --no-pub test/rowan_shader_render_test.dart test/rowan_surface_render_test.dart
```

The first fixture captures neutral and left/right turns at 32/64/320/640, with
attention, opening, idle, static-time and rectangular frames. The second captures
actual RowanAvatar widgets on light/dark app grounds at 32/64/320 and both fallback
themes. JSON binds source and pixel hashes, dimensions, coverage and timing.
An unchanged shader source is required during capture. LF shader line endings
keep source hashes stable across checkouts.
Without the variable, tests retain no capture files and use smaller pose fixtures.

These measurements are test-engine raster/readback observations. They do not
establish GPU throughput, sustained frame rate, battery cost, real mobile behavior
or the visual quality of the character. Visual review and real target-device
measurements remain separate from the pixel/control regression checks.
