#version 460 core
#include <flutter/runtime_effect.glsl>

// Original modeled Rowan: analytical solids, carved apertures and metal shells.
// Float layout: resolution[0:2], seconds[2], motion[3], gaze[4:6], yaw[6], mouth[7].
uniform vec2 uResolution;
uniform float uTime;
uniform float uMotion;
uniform vec2 uGaze;
uniform float uYaw;
uniform float uMouth;
out vec4 fragColor;

mat2 turn(float a) {
  float c = cos(a), s = sin(a);
  return mat2(c, -s, s, c);
}

float ellipsoid(vec3 p, vec3 r) {
  // Lower distance bound; unlike a ratio approximation it is finite at zero.
  return (length(p / r) - 1.0) * min(r.x, min(r.y, r.z));
}

float blendShape(float a, float b, float width) {
  float h = clamp(0.5 + 0.5 * (b - a) / width, 0.0, 1.0);
  return mix(b, a, h) - width * h * (1.0 - h);
}

vec2 nearer(vec2 a, vec2 b) { return a.x < b.x ? a : b; }

float bevelBox(vec3 p, vec3 size, float radius) {
  vec3 d = abs(p) - size;
  return length(max(d, 0.0)) + min(max(d.x, max(d.y, d.z)), 0.0) - radius;
}

float eyelid() {
  float phase = mod(max(uTime, 0.0), 5.8);
  float blink = smoothstep(0.0, 0.10, phase) *
      (1.0 - smoothstep(0.10, 0.24, phase));
  return clamp(uMotion, 0.0, 1.0) * blink;
}

vec3 modelPoint(vec3 p) {
  float idle = sin(uTime * 0.45) * 0.025 * clamp(uMotion, 0.0, 1.0);
  p.xz = turn(clamp(uYaw, -0.6, 0.6) + idle) * p.xz;
  return p;
}

float eyeAperture(vec3 p) {
  vec3 e = vec3(abs(p.x) - 0.207, p.y - 0.135, p.z - 0.405);
  e.y -= 0.18 * e.x;
  // Two intersecting volumes form an almond; both lids really close in 3D.
  float lift = mix(0.087, 0.140, eyelid());
  vec3 r = vec3(0.175, 0.145, 0.155);
  return max(ellipsoid(e - vec3(0.0, lift, 0.0), r),
      ellipsoid(e + vec3(0.0, lift, 0.0), r)) * 0.84;
}

vec2 scene(vec3 world) {
  vec3 p = modelPoint(world);
  vec3 q = p - vec3(0.0, 0.08, 0.0);
  // Continuous jaw taper keeps cheeks, jaw and chin one sculpted volume.
  float taper = 0.69 + 0.31 * smoothstep(-0.48, 0.10, p.y);
  q.x /= taper;
  float head = ellipsoid(q, vec3(0.475, 0.655, 0.365)) * 0.72;
  vec3 mask = p - vec3(0.0, -0.045, 0.155);
  mask.x /= taper;
  head = blendShape(head,
      ellipsoid(mask, vec3(0.40, 0.515, 0.275)) * 0.72, 0.045);
  vec3 cheek = vec3(abs(p.x), p.y, p.z) - vec3(0.242, -0.045, 0.222);
  head = blendShape(head, ellipsoid(cheek, vec3(0.126, 0.172, 0.130)), 0.045);
  // The bridge grows out of the brow; the tip is a separate small solid.
  float bridge = ellipsoid(p - vec3(0.0, 0.025, 0.408),
      vec3(0.045, 0.197, 0.067));
  float nose = ellipsoid(p - vec3(0.0, -0.106, 0.449),
      vec3(0.050, 0.043, 0.042));
  head = blendShape(head, blendShape(bridge, nose, 0.045), 0.068);
  vec3 brow = vec3(abs(p.x) - 0.207, p.y - 0.216, p.z - 0.282);
  brow.y -= brow.x * 0.21;
  head = blendShape(head, ellipsoid(brow,
      vec3(0.167, 0.072, 0.115)) * 0.90, 0.064);
  head = max(head, -eyeAperture(p));

  // Cupid bow, lower lip and a recessed animated mouth, all actual geometry.
  float lipLine = -0.286 - 0.009 * exp(-170.0 * p.x * p.x);
  vec3 upper = vec3(abs(p.x) - 0.040, p.y - lipLine - 0.002, p.z - 0.384);
  head = blendShape(head, ellipsoid(upper, vec3(0.069, 0.021, 0.024)) * 0.93, 0.018);
  head = blendShape(head, ellipsoid(p - vec3(0.0, -0.310, 0.382),
      vec3(0.096, 0.028, 0.026)), 0.020);
  float mouth = ellipsoid(vec3(p.x, p.y - lipLine + 0.008, p.z - 0.414),
      vec3(0.108, 0.006 + 0.029 * clamp(uMouth, 0.0, 1.0), 0.046)) * 0.93;
  head = max(head, -mouth);
  float nostril = ellipsoid(vec3(abs(p.x) - 0.029, p.y + 0.131, p.z - 0.473),
      vec3(0.012, 0.010, 0.017));
  head = max(head, -nostril);

  // One swept crescent shell replaces separate spherical crown lobes.
  vec3 c = p - vec3(-0.025, 0.48, -0.047);
  c.x -= 0.32 * c.y;
  float crest = ellipsoid(c, vec3(0.49, 0.74, 0.347)) * 0.74;
  float crescent = ellipsoid(p - vec3(0.384, 1.218, 0.03),
      vec3(0.375, 0.448, 0.50));
  crest = max(crest, -crescent);
  // Lift the forehead shell off the facial mask below the brow.
  crest = max(crest, (0.24 - p.y - 0.8 * p.x * p.x) * 0.65);
  float seam = (abs(p.x - 0.135 * sin(5.0 * (p.y - 0.30)) - 0.045)
      - 0.018) * 0.80;
  seam = max(seam, (0.43 - p.y) * 0.70);
  float plume = ellipsoid(p - vec3(0.255, 0.49, -0.060),
      vec3(0.30, 0.62, 0.285));
  plume = max(plume, -ellipsoid(p - vec3(0.105, 0.89, 0.065),
      vec3(0.26, 0.48, 0.42)));
  plume = max(plume, (0.29 - p.y) * 0.70);
  crest = blendShape(crest, plume, 0.020);
  float whole = blendShape(crest, head, 0.040);
  // Carved panel joints follow the cheeks into the jaw in a continuous shell.
  float flow = (abs(abs(p.x) - 0.285 - 0.09 * sin(4.0 * (p.y + 0.10)))
      - 0.011) * 0.90;
  flow = max(flow, 0.13 - p.z);
  float shell = max(whole, -min(seam, flow));
  vec2 result = nearer(vec2(whole + 0.019, 2.0), vec2(shell, 1.0));

  vec3 e = vec3(abs(p.x) - 0.207, p.y - 0.135, p.z - 0.280);
  float eye = max(ellipsoid(e, vec3(0.151, 0.103, 0.111)), eyeAperture(p));
  result = nearer(result, vec2(eye, 3.0));
  float neck = ellipsoid(p - vec3(0.0, -0.76, -0.045),
      vec3(0.166, 0.355, 0.182));
  result = nearer(result, vec2(neck, 2.0));
  // Open high collar: a hollow tapered shell, cut to a V at the front.
  vec3 coat = p - vec3(0.0, -1.30, -0.135);
  float jacket = ellipsoid(coat, vec3(0.92, 0.445, 0.34));
  float collar = max(ellipsoid(p - vec3(0.0, -0.96, -0.060),
      vec3(0.285, 0.41, 0.255)),
      -ellipsoid(p - vec3(0.0, -0.79, 0.075), vec3(0.206, 0.44, 0.238)));
  float v = p.y + 1.04 - 1.08 * abs(p.x);
  collar = max(collar, min(v * 0.67, (0.045 - p.z)));
  jacket = blendShape(jacket, collar, 0.025);
  result = nearer(result, vec2(jacket, 4.0));
  vec3 lapelPoint = vec3(abs(p.x) - 0.185, p.y + 1.075, p.z - 0.135);
  lapelPoint.xy = turn(-0.38) * lapelPoint.xy;
  float lapel = bevelBox(lapelPoint, vec3(0.056, 0.244, 0.075), 0.010);
  lapel = max(lapel, (lapelPoint.y - 0.20 + 0.60 * lapelPoint.x) * 0.85);
  return nearer(result, vec2(lapel, 5.0));
}

vec3 normalAt(vec3 p) {
  vec2 e = vec2(0.0014, 0.0);
  vec3 gradient = vec3(
      scene(p + e.xyy).x - scene(p - e.xyy).x,
      scene(p + e.yxy).x - scene(p - e.yxy).x,
      scene(p + e.yyx).x - scene(p - e.yyx).x);
  float norm2 = dot(gradient, gradient);
  return norm2 > 1e-12 ? gradient * inversesqrt(norm2) : vec3(0.0, 0.0, 1.0);
}

vec3 surfaceColor(vec3 world, float material) {
  vec3 p = modelPoint(world);
  vec3 color = vec3(0.61, 0.64, 0.67);
  if (material > 4.5) {
    color = vec3(0.046, 0.054, 0.068);
  } else if (material > 3.5) {
    color = vec3(0.028, 0.034, 0.044);
  } else if (material > 2.5) {
    float eyeSide = p.x < 0.0 ? -1.0 : 1.0;
    vec2 center = vec2(eyeSide * 0.207, 0.135) +
        clamp(uGaze, -1.0, 1.0) * vec2(0.032, 0.019);
    float iris = length((p.xy - center) / vec2(0.049, 0.049));
    vec3 irisColor = mix(vec3(0.18, 0.20, 0.40), vec3(0.08, 0.30, 0.34),
        smoothstep(-0.1, 0.1, p.x));
    color = mix(vec3(0.09, 0.13, 0.15), irisColor,
        1.0 - smoothstep(0.82, 1.0, iris));
    color *= 0.075 + 0.925 * smoothstep(0.38, 0.48, iris);
  } else if (material > 1.5) {
    color = vec3(0.058, 0.079, 0.094);
    if (p.y < -0.48) {
      float ribbon = smoothstep(0.015, 0.030,
          abs(p.x - 0.07 * sin(7.0 * (p.y + 0.70))));
      color = mix(color, vec3(0.29, 0.34, 0.38), ribbon);
    }
  } else {
    float lips = (1.0 - smoothstep(0.026, 0.045, abs(p.y + 0.294))) *
        (1.0 - smoothstep(0.089, 0.127, abs(p.x))) * step(0.36, p.z);
    color = mix(color, vec3(0.29, 0.33, 0.37), lips * 0.60);
  }
  return color;
}

void main() {
  vec2 size = max(uResolution, vec2(1.0));
  vec2 uv = (FlutterFragCoord().xy * 2.0 - size) / min(size.x, size.y);
  uv.y = -uv.y;
  vec3 origin = vec3(uv.x * 1.30, uv.y * 1.30 + 0.02, 3.4);
  vec3 direction = vec3(0.0, 0.0, -1.0);
  float travel = 2.65;
  vec2 sampleValue = vec2(1.0, 0.0);
  vec3 point = origin;
  // Fixed work bound, no texture fetch, recursion, or unbounded iteration.
  for (int step = 0; step < 96; step++) {
    point = origin + direction * travel;
    sampleValue = scene(point);
    if (sampleValue.x < 0.0011 || travel > 4.12) break;
    travel += max(sampleValue.x * 0.85, 0.0006);
  }
  if (sampleValue.x >= 0.0011 || travel > 4.12) {
    fragColor = vec4(0.0);
    return;
  }
  vec3 normal = normalAt(point);
  vec3 view = -direction;
  vec3 key = normalize(vec3(-0.75, 1.25, 1.65));
  vec3 fill = normalize(vec3(1.1, 0.35, 0.90));
  float diffuse = max(dot(normal, key), 0.0);
  float secondary = max(dot(normal, fill), 0.0);
  float ao = clamp(scene(point + normal * 0.035).x / 0.027, 0.25, 1.0);
  vec3 base = surfaceColor(point, sampleValue.y);
  vec3 color = base * (0.16 + 0.67 * diffuse + 0.16 * secondary) * ao;
  float gloss = sampleValue.y > 3.5 ? 0.015 : 0.52;
  float power = sampleValue.y > 2.5 && sampleValue.y < 3.5 ? 100.0 : 54.0;
  float highlight = pow(max(dot(normal, normalize(key + view)), 0.0), power);
  float broad = pow(max(dot(normal, normalize(fill + view)), 0.0), 20.0);
  color += vec3(0.89, 0.93, 0.98) * (highlight + broad * 0.14) * gloss * ao;
  if (sampleValue.y > 2.5 && sampleValue.y < 3.5) {
    float glint = pow(max(dot(normal, normalize(vec3(-0.18, 0.24, 1.0))), 0.0), 230.0);
    color += vec3(0.95, 0.98, 1.0) * glint;
  }
  float rim = pow(1.0 - max(dot(normal, view), 0.0), 2.6);
  vec3 edge = mix(vec3(0.34, 0.14, 0.49), vec3(0.06, 0.43, 0.47),
      smoothstep(-0.25, 0.25, normal.x));
  color += edge * rim * 0.47;
  // Art colors never encode a task's completion or evidence verdict.
  fragColor = vec4(sqrt(clamp(color, 0.0, 1.0)), 1.0);
}
