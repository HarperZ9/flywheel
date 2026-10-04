import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host_noise.dart';

/// Exact golden comparison first; on a mismatch, accept only host
/// rasterization noise as defined in host_noise.dart. A rejected mismatch
/// fails with Flutter's normal failure images plus the measured noise figures.
class HostNoiseComparator extends LocalFileComparator {
  HostNoiseComparator(super.testFile);

  @override
  Future<bool> compare(Uint8List imageBytes, Uri golden) async {
    final goldenBytes = await getGoldenBytes(golden);
    final result =
        await GoldenFileComparator.compareLists(imageBytes, goldenBytes);
    if (result.passed) {
      result.dispose();
      return true;
    }
    final verdict = await _verdict(Uint8List.fromList(goldenBytes), imageBytes);
    if (verdict != null && verdict.accepted) {
      result.dispose();
      debugPrint('$golden: ${verdict.describe()}');
      return true;
    }
    final error = await generateFailureOutput(result, golden, basedir);
    result.dispose();
    throw FlutterError(
        '$error\n${verdict?.describe() ?? 'Host-noise check: sizes differ.'}');
  }
}

Future<HostNoiseVerdict?> _verdict(Uint8List golden, Uint8List test) async {
  final a = await _rgba(golden);
  final b = await _rgba(test);
  if (a.width != b.width || a.height != b.height) return null;
  return hostNoiseVerdict(a.bytes, b.bytes, a.width, a.height);
}

Future<({Uint8List bytes, int width, int height})> _rgba(Uint8List png) async {
  final codec = await ui.instantiateImageCodec(png);
  final frame = await codec.getNextFrame();
  final image = frame.image;
  final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  final out = (
    bytes: data!.buffer.asUint8List(),
    width: image.width,
    height: image.height
  );
  image.dispose();
  codec.dispose();
  return out;
}
