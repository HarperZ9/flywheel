#version 460 core
#include <flutter/runtime_effect.glsl>

// Rowan aperture study, not a shipping character. Original analytical volume.
// Site references: generative-field aperture and Atelier halo/crisp-ink passes.
// Uniform slots unchanged: size[0:2], time[2], motion[3], attention[4:6], yaw[6],
// expression[7]. The legacy uMouth slot opens the aperture; there are no lips.
uniform vec2 uResolution;
uniform float uTime;
uniform float uMotion;
uniform vec2 uGaze;
uniform float uYaw;
uniform float uMouth;
out vec4 fragColor;
const float PI = 3.14159265359;

mat2 turn(float a) {
  float c = cos(a), s = sin(a);
  return mat2(c, -s, s, c);
}
float clockTime() { return max(uTime, 0.0) * clamp(uMotion, 0.0, 1.0); }
float expression() { return clamp(uMouth, 0.0, 1.0); }
float grain(vec2 p) {
  // Fixed Rowan study seed 37. Arithmetic grain, never a sampled image.
  return fract(sin(dot(p + 37.0, vec2(127.1, 311.7))) * 43758.5453);
}
vec3 modelPoint(vec3 p) {
  float idle = 0.035 * sin(clockTime() * 0.65);
  p.xz = turn(clamp(uYaw, -0.6, 0.6) + idle) * p.xz;
  p.xy = turn(-0.13) * p.xy;
  return p;
}
float ringRadius(float a) {
  return 0.475 + 0.025 * cos(a + 0.6) + 0.014 * sin(3.0 * a) +
      0.028 * expression();
}
float ringDepth(float a) { return 0.048 * sin(2.0 * a + 0.4); }
float aperture(vec3 p) {
  float radius = length(p.xy);
  // Ring inner radius is at least .236; this empty guard never approaches a hit.
  if (radius < 0.22) return max(0.23 - radius, abs(p.z) - 0.20) * 0.65;
  float a = atan(p.y, p.x);
  float thickness = 0.172 + 0.016 * sin(a - 0.5) +
      0.012 * cos(3.0 * a + 0.8) - 0.022 * expression();
  vec2 tube = vec2(radius - ringRadius(a), (p.z - ringDepth(a)) * 1.40);
  return (length(tube) - thickness) * 0.62;
}
vec2 scene(vec3 world) {
  return vec2(aperture(modelPoint(world)), 1.0);
}
vec3 coreLight(vec3 world) {
  vec3 center = vec3(-0.015, -0.024, -0.065);
  center.xy += clamp(uGaze, -1.0, 1.0) * 0.028;
  vec3 offset = modelPoint(world) - center;
  vec3 axis = modelPoint(vec3(0.0, 0.0, -1.0));
  vec3 radial = offset - axis * dot(offset, axis);
  // Analytic ray integral of a small 3D Gaussian emitter: no opaque bead edge.
  float width = 0.056 + 0.004 * sin(clockTime());
  float r2 = dot(radial, radial);
  float cloud = exp(-r2 / (2.0 * width * width));
  float halo = exp(-r2 / 0.026);
  return vec3(0.937, 0.671, 0.188) * (0.20 * cloud + 0.018 * halo) +
      vec3(0.965, 0.945, 0.855) * cloud * cloud * 0.75;
}
vec3 normalAt(vec3 p) {
  vec2 e = vec2(0.0015, 0.0);
  vec3 g = vec3(scene(p + e.xyy).x - scene(p - e.xyy).x,
      scene(p + e.yxy).x - scene(p - e.yxy).x,
      scene(p + e.yyx).x - scene(p - e.yyx).x);
  return g * inversesqrt(max(dot(g, g), 1e-12));
}
vec3 lightThreads(vec3 world, vec3 normal, float detail) {
  vec3 p = modelPoint(world);
  float a = atan(p.y, p.x);
  float r = length(p.xy);
  float v = atan((p.z - ringDepth(a)) * 1.40, r - ringRadius(a));
  float drift = clockTime() * 0.08;
  // Flow along the rounded opening, then a sparse seven-fold crossing weave.
  float flowing = a + 0.60 * cos(v) +
      0.10 * sin(3.0 * a + 2.0 * v) + 0.014 * sin(11.0 * a - 2.0 * v);
  float filament = 0.5 + 0.5 * cos(flowing * detail + v * 3.0 + drift);
  float crossing = 0.5 + 0.5 * cos(v * 9.0 + sin(a * 7.0) * 0.12);
  float ink = pow(filament, 15.0);
  float halo = pow(filament, 2.5) * 0.12;
  float fine = pow(crossing, 32.0) * 0.05;
  float facing = max(dot(normal, normalize(vec3(-0.4, 0.7, 1.3))), 0.0);
  float edge = pow(1.0 - max(normal.z, 0.0), 2.0);
  // Ember ink and warm white from the site's palette; one quiet spectral edge.
  vec3 amber = vec3(0.937, 0.671, 0.188);
  vec3 warmWhite = vec3(0.965, 0.812, 0.561);
  vec3 inkColor = mix(amber, warmWhite, 0.12 + 0.28 * facing);
  float spectral = smoothstep(0.40, 0.54, p.x) * smoothstep(-0.25, 0.18, p.y);
  vec3 cool = mix(vec3(0.50, 0.28, 0.88), vec3(0.16, 0.78, 0.88),
      smoothstep(-0.10, 0.40, p.y));
  inkColor = mix(inkColor, cool, spectral * 0.82);
  vec3 color = vec3(0.014, 0.009, 0.004) * (0.3 + facing);
  color += inkColor * (ink * 0.75 + halo + fine) * (0.48 + 0.52 * facing);
  color += inkColor * edge * 0.10;
  float surfaceGrain = grain(floor(p.xy * 1800.0) + floor(p.z * 997.0));
  return color * (0.94 + 0.12 * surfaceGrain);
}
void main() {
  vec2 size = max(uResolution, vec2(1.0));
  vec2 uv = (FlutterFragCoord().xy * 2.0 - size) / min(size.x, size.y);
  uv.y = -uv.y;
  vec3 origin = vec3(uv * 0.98, 2.2);
  vec3 direction = vec3(0.0, 0.0, -1.0);
  float travel = 1.62;
  vec2 sampleValue = vec2(1.0, 0.0);
  vec3 point = origin;
  // One surface and an analytic light volume; 52 steps, no textures or recursion.
  for (int step = 0; step < 52; step++) {
    point = origin + direction * travel;
    sampleValue = scene(point);
    if (sampleValue.x < 0.0013 || travel > 2.83) break;
    travel += max(sampleValue.x * 0.90, 0.0008);
  }
  if (sampleValue.x >= 0.0013 || travel > 2.83) {
    float r = length(uv * 0.98);
    if (r > 0.92) { fragColor = vec4(0.0); return; }
    float haze = exp(-36.0 * abs(r - 0.635)) * 0.008;
    // The study's art ground is black; no transparent glow is mistaken for ink.
    vec3 glow = vec3(0.82, 0.50, 0.17) * haze + coreLight(vec3(uv * 0.98, 0.0));
    glow = vec3(1.0) - exp(-glow * 1.25);
    fragColor = vec4(sqrt(clamp(glow, 0.0, 1.0)), 1.0);
    return;
  }
  vec3 normal = normalAt(point);
  // Integer winding counts keep both atan branch seams continuous.
  float detail = floor(mix(36.0, 182.0,
      smoothstep(32.0, 640.0, min(size.x, size.y))) + 0.5);
  vec3 color = lightThreads(point, normal, detail);
  color = vec3(1.0) - exp(-color * 1.25);
  fragColor = vec4(sqrt(clamp(color, 0.0, 1.0)), 1.0);
}
