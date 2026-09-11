#version 460 core
#include <flutter/runtime_effect.glsl>

// Original Rowan volume. Retro Studio references at dce83e300ef1a504:
// Twisted Torus Coil: relief, key/fill, AO, Fresnel and specular material.
// Satin Stitch Aperture: directional silk; Gold Ground: seeded facets; retro-engine: ordered palette and phosphor.
// Eight slots: size[0:2], time[2], motion[3], attention[4:6], yaw[6], opening[7].
// uGaze/uMouth retain the established slot names; no facial landmarks are modeled.
uniform vec2 uResolution;
uniform float uTime;
uniform float uMotion;
uniform vec2 uGaze;
uniform float uYaw;
uniform float uMouth;
out vec4 fragColor;
const float PI = 3.14159265359;
const float FIELD_SCALE = 0.42;

mat2 turn(float a) {
  float c = cos(a), s = sin(a);
  return mat2(c, -s, s, c);
}
float clockTime() { return max(uTime, 0.0) * clamp(uMotion, 0.0, 1.0); }
float opening() { return clamp(uMouth, 0.0, 1.0); }
float grain(vec2 p) {
  return fract(sin(dot(p + 37.0, vec2(127.1, 311.7))) * 43758.5453);
}
vec3 modelPoint(vec3 p) {
  p.xz = turn(clamp(uYaw, -0.6, 0.6) + 0.035 * sin(clockTime() * 0.65)) * p.xz;
  p.xy = turn(-0.13) * p.xy;
  return p;
}
float ringRadius(float a) {
  return 0.475 + 0.025 * cos(a + 0.6) + 0.014 * sin(3.0 * a) + 0.028 * opening();
}
float ringDepth(float a) { return 0.048 * sin(2.0 * a + 0.4); }
vec2 field(vec3 p) {
  float r = length(p.xy);
  // All modeled layers stay outside r=.20. Avoid the polar singularity.
  if (r < 0.18) return vec2(max(0.195 - r, abs(p.z) - 0.22), 0.0);
  float a = atan(p.y, p.x);
  float major = ringRadius(a), depth = ringDepth(a);
  vec2 q = vec2(r - major, (p.z - depth) * 1.40);
  float section = length(q);
  // The central tube is safely interior; its angle is immaterial to the boundary.
  float v = section > 0.08 ? atan(q.y, q.x) : 0.0;
  float thickness = 0.170 + 0.016 * sin(a - 0.5) +
      0.012 * cos(3.0 * a + 0.8) - 0.022 * opening();
  float pleat = 0.007 * cos(9.0 * a + 2.0 * v + 0.5);
  vec2 result = vec2(section - thickness - pleat, 1.0);
  // A separate rounded inner lip sits behind the main weave, creating parallax
  // and a real occluding recess rather than a painted concentric stripe.
  vec2 lip = vec2(r - (major - 0.190 + 0.010 * opening()),
      (p.z - depth + 0.095) * 1.25);
  float lipDistance = length(lip) - 0.022;
  if (lipDistance < result.x) result = vec2(lipDistance, 2.0);
  return result;
}
vec2 scene(vec3 p) {
  vec2 d = field(modelPoint(p));
  return vec2(d.x * FIELD_SCALE, d.y);
}
vec3 coreLight(vec3 world) {
  vec3 center = vec3(-0.015, -0.024, -0.065);
  center.xy += clamp(uGaze, -1.0, 1.0) * 0.028;
  vec3 offset = modelPoint(world) - center;
  vec3 axis = modelPoint(vec3(0.0, 0.0, -1.0));
  vec3 radial = offset - axis * dot(offset, axis);
  float width = 0.056 + 0.004 * sin(clockTime());
  float r2 = dot(radial, radial);
  float cloud = exp(-r2 / (2.0 * width * width));
  return vec3(0.937, 0.671, 0.188) * (0.20 * cloud + 0.018 * exp(-r2 / 0.026)) +
      vec3(0.965, 0.945, 0.855) * cloud * cloud * 0.75;
}
vec3 normalAt(vec3 p) {
  vec2 e = vec2(0.0015, 0.0);
  vec3 g = vec3(scene(p + e.xyy).x - scene(p - e.xyy).x,
      scene(p + e.yxy).x - scene(p - e.yxy).x,
      scene(p + e.yyx).x - scene(p - e.yyx).x);
  return g * inversesqrt(max(dot(g, g), 1e-12));
}
float occlusion(vec3 p, vec3 n) {
  float occ = 0.0, weight = 1.0;
  // Four fixed local probes. This is a shading heuristic, not global illumination.
  for (int i = 0; i < 4; i++) {
    float h = 0.018 + 0.028 * float(i);
    occ += max(h - scene(p + n * h).x / FIELD_SCALE, 0.0) * weight;
    weight *= 0.62;
  }
  return clamp(1.0 - occ * 5.0, 0.30, 1.0);
}
vec3 material(vec3 world, vec3 n, float part, float detail) {
  vec3 p = modelPoint(world);
  float a = atan(p.y, p.x), r = length(p.xy);
  float v = atan((p.z - ringDepth(a)) * 1.40, r - ringRadius(a));
  float flowing = a + 0.60 * cos(v) + 0.10 * sin(3.0 * a + 2.0 * v) +
      0.014 * sin(11.0 * a - 2.0 * v);
  float filament = 0.5 + 0.5 * cos(flowing * detail + 3.0 * v + clockTime() * 0.08);
  float crossing = 0.5 + 0.5 * cos(9.0 * v + 0.12 * sin(7.0 * a));
  float ink = pow(filament, 12.0), fine = pow(crossing, 28.0);
  vec3 key = normalize(vec3(-0.65, 0.80, 1.25));
  vec3 fill = normalize(vec3(0.80, -0.20, 0.70));
  float diffuse = max(dot(n, key), 0.0), bounce = max(dot(n, fill), 0.0);
  float fresnel = pow(clamp(1.0 - n.z, 0.0, 1.0), 3.0);
  float broad = pow(max(dot(n, normalize(key + vec3(0.0, 0.0, 1.0))), 0.0), 18.0);
  float glint = pow(max(dot(n, normalize(fill + vec3(0.0, 0.0, 1.0))), 0.0), 72.0);
  float ao = occlusion(world, n);
  vec3 amber = vec3(1.0, 0.54, 0.38), silk = vec3(0.957, 0.925, 1.0);
  float spectral = smoothstep(0.28, 0.54, p.x) * smoothstep(-0.35, 0.22, p.y);
  vec3 cool = mix(vec3(0.50, 0.28, 0.88), vec3(0.16, 0.78, 0.88),
      smoothstep(-0.10, 0.40, p.y));
  vec3 dye = mix(vec3(0.706, 0.125, 0.471), amber, 0.28 + 0.66 * diffuse);
  dye = mix(dye, cool, spectral * 0.90);
  // Satin changes tone with orientation; ridges catch light, valleys keep depth.
  float silkTurn = 0.5 + 0.5 * cos(2.0 * a + 2.0 * v - 0.6);
  float weave = 0.56 + 0.44 * filament;
  // Closed toroidal cells, integer counts on both angle seams. Seeded facet tone
  // follows Gold Ground's cell variation, with weaving retained over the facets.
  vec2 tile = vec2((a / (2.0 * PI) + 0.5) * 48.0,
      (v / (2.0 * PI) + 0.5) * 16.0);
  vec2 cell = mod(floor(tile), vec2(48.0, 16.0));
  float seed = grain(cell);
  vec2 local = fract(tile);
  float edge = min(min(local.x, 1.0 - local.x), min(local.y, 1.0 - local.y));
  float inset = smoothstep(0.015, 0.075, edge);
  float tessera = mix(1.0, (0.78 + seed * 0.36) * (0.82 + 0.18 * inset),
      smoothstep(48.0, 120.0, detail));
  vec3 color = dye * (0.030 + 0.24 * diffuse + 0.040 * bounce) * weave * ao * tessera;
  color += silk * broad * (0.045 + 0.16 * ink) * ao;
  color += dye * (ink * (0.22 + 0.24 * diffuse) + fine * 0.016) *
      (0.42 + 0.58 * silkTurn) * ao;
  color += mix(silk, cool, spectral) * glint * 0.19 * ao;
  color += mix(vec3(0.31, 0.12, 0.46), dye, diffuse) * fresnel * 0.12;
  if (part > 1.5) {
    float etch = pow(0.5 + 0.5 * cos(72.0 * a + 3.0 * v), 18.0);
    color = dye * (0.055 + 0.18 * diffuse + 0.20 * broad) * ao;
    color += dye * (0.10 * etch + 0.16 * fresnel);
  }
  return color * (0.96 + 0.08 * grain(floor(p.xy * 1800.0) + floor(p.z * 997.0)));
}
vec3 retroColor(int i) {
  if (i == 0) return vec3(0.0392, 0.0235, 0.0784);
  if (i == 1) return vec3(0.1020, 0.0471, 0.1882);
  if (i == 2) return vec3(0.2510, 0.0784, 0.3765);
  if (i == 3) return vec3(0.7059, 0.1255, 0.4706);
  if (i == 4) return vec3(1.0, 0.3059, 0.6275);
  if (i == 5) return vec3(1.0, 0.5412, 0.3765);
  if (i == 6) return vec3(0.3137, 0.8627, 0.9412);
  return vec3(0.9569, 0.9255, 1.0);
}
float bayer4(vec2 p) {
  vec2 q = mod(floor(p), 4.0);
  vec2 low = mod(q, 2.0), high = floor(q / 2.0);
  float a = 2.0 * low.x + 3.0 * low.y - 4.0 * low.x * low.y;
  float b = 2.0 * high.x + 3.0 * high.y - 4.0 * high.x * high.y;
  return (4.0 * a + b + 0.5) / 16.0;
}
vec3 finish(vec3 color, vec2 pixel, float size) {
  color = sqrt(clamp(vec3(1.0) - exp(-color * 1.25), 0.0, 1.0));
  // The site's eight Outrun inks. This bounded single-pass approximation uses
  // weighted RGB brackets rather than its CPU OKLab search and resampling.
  vec3 first = vec3(0.0), second = first;
  float d1 = 100.0, d2 = 100.0;
  for (int i = 0; i < 8; i++) {
    vec3 ink = retroColor(i), delta = (color - ink) * vec3(0.75, 1.0, 0.80);
    float d = dot(delta, delta);
    if (d < d1) { second = first; d2 = d1; first = ink; d1 = d; }
    else if (d < d2) { second = ink; d2 = d; }
  }
  vec3 span = second - first;
  float amount = clamp(dot(color - first, span) / max(dot(span, span), 1e-5), 0.0, 1.0);
  vec3 ordered = mix(first, second, step(bayer4(pixel), amount));
  float visible = smoothstep(0.012, 0.12, max(color.r, max(color.g, color.b)));
  color = mix(color, ordered, 0.38 * visible);
  // Bright crests fill the beam; dim rows retain a faint grille texture.
  float strength = smoothstep(80.0, 320.0, size);
  float lum = dot(color, vec3(0.299, 0.587, 0.114));
  color *= 1.0 - strength * 0.10 * (1.0 - lum) * (0.5 + 0.5 * cos(pixel.y * PI));
  return clamp(color, 0.0, 1.0);
}
void main() {
  vec2 size = max(uResolution, vec2(1.0));
  float extent = min(size.x, size.y);
  vec2 pixel = FlutterFragCoord().xy;
  float grid = max(64.0, min(extent, 240.0));
  vec2 sourcePixel = (floor((pixel - size * 0.5) * grid / extent) + 0.5) * extent / grid;
  vec2 uv = sourcePixel * 2.0 / extent;
  uv.y = -uv.y;
  if (length((pixel * 2.0 - size) / extent * 0.98) > 0.92) { fragColor = vec4(0.0); return; }
  vec3 origin = vec3(uv * 0.98, 2.2), direction = vec3(0.0, 0.0, -1.0);
  float travel = 1.62;
  vec2 sampleValue = vec2(1.0, 0.0);
  vec3 point = origin;
  // At most 64 march + 6 normal + 4 AO field evaluations per visible pixel.
  for (int step = 0; step < 64; step++) {
    point = origin + direction * travel;
    sampleValue = scene(point);
    if (sampleValue.x < 0.0013 || travel > 2.83) break;
    travel += max(sampleValue.x * 0.90, 0.0008);
  }
  vec3 color;
  if (sampleValue.x >= 0.0013 || travel > 2.83) {
    float haze = exp(-36.0 * abs(length(uv * 0.98) - 0.635)) * 0.008;
    color = vec3(0.82, 0.50, 0.17) * haze + coreLight(vec3(uv * 0.98, 0.0));
  } else {
    float detail = floor(mix(32.0, 108.0, smoothstep(32.0, 640.0, extent)) + 0.5);
    color = material(point, normalAt(point), sampleValue.y, detail);
  }
  fragColor = vec4(finish(color, pixel, extent), 1.0);
}
