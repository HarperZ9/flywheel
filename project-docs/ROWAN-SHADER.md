# Rowan's modeled identity

Rowan is the same assistant in chat, native tasks and presentation. The canonical
RowanAvatar draws procedural character geometry through Flutter's FragmentProgram
and Paint.shader. The shader contains the model and shading; no portrait bitmap,
image sampler, video or WebView supplies the character.

Chat uses static 32-pixel avatars and a 64-pixel welcome character. The Studio
contains the same renderer at up to 320 pixels, with a keyboard-accessible Turn
slider, pointer gaze and an explicit Motion switch. This does not connect mouth
movement to speech or claim automatic lip synchronization.

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

Unsupported or failed shader loading produces a simple Canvas drawing. Its
semantic label and tooltip name the fallback, and Studio explicitly reports that
the modeled renderer is unavailable. Pose and motion controls are disabled there.
While loading, the placeholder and Studio explain why controls are unavailable.
The fallback does not use a PNG or pretend to be a 3D model.

Receipt verdicts and model/provider choice remain separate UI controls. Neither
changes the character's identity or supplies a success-colored avatar.

## Shader contract

The shader is declared under flutter.shaders in pubspec.yaml. Uniform ordering is
shared with RowanShaderPainter:

| Float slots | GLSL uniform | Meaning |
| --- | --- | --- |
| 0, 1 | vec2 uResolution | Logical canvas width and height |
| 2 | float uTime | Elapsed active animation seconds |
| 3 | float uMotion | 0 for static, 1 for optional motion |
| 4, 5 | vec2 uGaze | Bounded horizontal/vertical gaze, each -1 to 1 |
| 6 | float uYaw | Turn in radians, -0.6 to 0.6 |
| 7 | float uMouth | Procedural mouth pose, 0 to 1 |

Nonfinite pose values become zero; finite values are clamped to this contract.
Output is premultiplied RGBA with transparent background. The integration uses
Paint.shader, not the Impeller-only ImageFilter.shader path.
The initial kernel uses at most 96 ray-march steps. Its reviewed source SHA-256 is
`c2e10731a77771b4b870ec746142adfa41a6a193d9768f71784b9ca05d797020`.
Capture receipts record the actual source hash again on each run.

## Verification and capture

Run flutter analyze and the full flutter test suite in desktop. Focused tests
exercise actual shader loading, output coverage, pose differences, static idle
behavior, reduced motion, app state, scrolling, keyboard controls and narrow
layouts. The fallback test injects a failed loader; rendering tests use the real
compiled FragmentProgram.

To retain native test-engine frames, set ROWAN_CAPTURE_DIR to a local output
directory and run:

```
flutter test --no-pub test/rowan_shader_render_test.dart --reporter expanded
```

The fixture captures neutral and left/right yaw at 32/64/320/640, with 320-pixel
gaze, blink and mouth variations. Its JSON receipt binds source and pixel hashes, dimensions, coverage
and raster/readback timing. An unchanged shader source is required during capture.
Without the variable, tests retain no capture files and use smaller pose fixtures.

These measurements are test-engine raster/readback observations. They do not
establish GPU throughput, sustained frame rate, battery cost, real mobile behavior
or the visual quality of the character. Visual review and real target-device
measurements remain separate from the pixel/control regression checks.
