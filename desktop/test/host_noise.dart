import 'dart:math' as math;
import 'dart:typed_data';

/// Decides whether a golden mismatch is host rasterization noise.
///
/// The same SDK, runner image and bundled fonts still rendered every Windows
/// golden with small edge differences on one desktop-ci runner (run
/// 37154354793, attempt 1, 2026-10-03), and the rerun on another host matched
/// exactly. Across all six failing images the measured noise was:
///
/// * largest channel delta: 33 of 255;
/// * differing pixels: at most 0.18% of the frame;
/// * every differing pixel lay inside the golden's 3x3 neighborhood range,
///   at most 5 levels outside it. Antialiasing moves edge coverage between
///   neighboring colors; it does not invent new ones.
///
/// The limits below sit above those measurements with margin and far below a
/// real change: a 1 px frame shift reaches delta 244, a 6-level tint on one
/// panel touches 12.7% of the frame, erased text reaches delta 233 outside
/// the neighborhood range, and a swapped 24 px block lands 32 levels outside
/// it. A change that keeps every pixel between its golden neighbors, under
/// delta 48 and under 0.5% of the frame, is not detected; that is the stated
/// cost of accepting host noise.
class HostNoiseLimits {
  const HostNoiseLimits({
    this.maxChannelDelta = 48,
    this.maxOutsideNeighborhood = 8,
    this.maxDifferingFraction = 0.005,
  });

  final int maxChannelDelta;
  final int maxOutsideNeighborhood;
  final double maxDifferingFraction;
}

class HostNoiseVerdict {
  const HostNoiseVerdict({
    required this.accepted,
    required this.maxChannelDelta,
    required this.maxOutsideNeighborhood,
    required this.differingPixels,
    required this.totalPixels,
  });

  final bool accepted;
  final int maxChannelDelta;
  final int maxOutsideNeighborhood;
  final int differingPixels;
  final int totalPixels;

  double get differingFraction =>
      totalPixels == 0 ? 0 : differingPixels / totalPixels;

  String describe() => 'Host-noise check '
      '${accepted ? 'accepted' : 'rejected'} the difference: '
      'max channel delta $maxChannelDelta, '
      'max distance outside the golden 3x3 neighborhood '
      '$maxOutsideNeighborhood, '
      '$differingPixels of $totalPixels pixels differ '
      '(${(differingFraction * 100).toStringAsFixed(3)}%).';
}

/// Compares two RGBA buffers of the same [width] and [height].
HostNoiseVerdict hostNoiseVerdict(
  Uint8List golden,
  Uint8List test,
  int width,
  int height, {
  HostNoiseLimits limits = const HostNoiseLimits(),
}) {
  final total = width * height;
  if (golden.length != total * 4 || test.length != total * 4) {
    return HostNoiseVerdict(
        accepted: false,
        maxChannelDelta: 255,
        maxOutsideNeighborhood: 255,
        differingPixels: total,
        totalPixels: total);
  }
  var maxDelta = 0, maxOutside = 0, differing = 0;
  for (var y = 0; y < height; y++) {
    for (var x = 0; x < width; x++) {
      final i = (y * width + x) * 4;
      var pixelDiffers = false;
      for (var c = 0; c < 4; c++) {
        final delta = (golden[i + c] - test[i + c]).abs();
        if (delta == 0) continue;
        pixelDiffers = true;
        maxDelta = math.max(maxDelta, delta);
        maxOutside = math.max(maxOutside,
            _outsideNeighborhood(golden, width, height, x, y, c, test[i + c]));
      }
      if (pixelDiffers) differing++;
    }
  }
  final accepted = maxDelta <= limits.maxChannelDelta &&
      maxOutside <= limits.maxOutsideNeighborhood &&
      differing <= total * limits.maxDifferingFraction;
  return HostNoiseVerdict(
      accepted: accepted,
      maxChannelDelta: maxDelta,
      maxOutsideNeighborhood: maxOutside,
      differingPixels: differing,
      totalPixels: total);
}

int _outsideNeighborhood(Uint8List golden, int width, int height, int x, int y,
    int channel, int value) {
  var lo = 255, hi = 0;
  for (var ny = math.max(0, y - 1); ny <= math.min(height - 1, y + 1); ny++) {
    for (var nx = math.max(0, x - 1); nx <= math.min(width - 1, x + 1); nx++) {
      final v = golden[(ny * width + nx) * 4 + channel];
      lo = math.min(lo, v);
      hi = math.max(hi, v);
    }
  }
  if (value < lo) return lo - value;
  if (value > hi) return value - hi;
  return 0;
}
