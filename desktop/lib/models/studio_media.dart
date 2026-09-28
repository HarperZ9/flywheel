import 'dart:convert';
import 'dart:math' as math;

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';

const _maxMediaBytes = 32 * 1024 * 1024;

Uint8List _checkedBytes(Object? encoded, Object? expectedHash) {
  if (encoded is! String ||
      encoded.length > ((_maxMediaBytes + 2) ~/ 3) * 4 ||
      expectedHash is! String ||
      !RegExp(r'^[0-9a-f]{64}$').hasMatch(expectedHash)) {
    throw const FormatException('Media or full receipt hash is missing.');
  }
  final bytes = base64Decode(encoded);
  if (bytes.isEmpty ||
      bytes.length > _maxMediaBytes ||
      sha256.convert(bytes).toString() != expectedHash) {
    throw const FormatException('Media bytes do not match the receipt.');
  }
  return bytes.asUnmodifiableView();
}

/// Receipt-bound audio. Peaks are measured from its PCM samples, not a model.
class StudioAudio {
  StudioAudio._(this.bytes, this.sha256Hex, this.sampleRate, this.duration,
      List<double> peaks)
      : peaks = List.unmodifiable(peaks);

  final Uint8List bytes;
  final String sha256Hex;
  final int sampleRate;
  final Duration duration;
  final List<double> peaks;

  factory StudioAudio.fromResult(Map<String, dynamic> result) {
    final receipt = result['receipt'];
    final hash = receipt is Map ? receipt['wav_sha256'] : null;
    final bytes = _checkedBytes(result['wav_b64'], hash);
    final data = ByteData.sublistView(bytes);
    String tag(int i) =>
        ascii.decode(bytes.sublist(i, i + 4), allowInvalid: true);
    if (bytes.length < 44 ||
        tag(0) != 'RIFF' ||
        tag(8) != 'WAVE' ||
        data.getUint32(4, Endian.little) != bytes.length - 8) {
      throw const FormatException('Invalid WAV container.');
    }
    int? channels, rate, align, start, count;
    var cursor = 12;
    while (cursor + 8 <= bytes.length) {
      final size = data.getUint32(cursor + 4, Endian.little);
      final body = cursor + 8;
      if (body + size > bytes.length) {
        throw const FormatException('Truncated WAV chunk.');
      }
      if (tag(cursor) == 'fmt ') {
        if (rate != null ||
            size < 16 ||
            data.getUint16(body, Endian.little) != 1 ||
            data.getUint16(body + 14, Endian.little) != 16) {
          throw const FormatException('Expected a 16-bit PCM WAV.');
        }
        channels = data.getUint16(body + 2, Endian.little);
        rate = data.getUint32(body + 4, Endian.little);
        align = data.getUint16(body + 12, Endian.little);
        if (channels < 1 ||
            channels > 2 ||
            rate < 8000 ||
            rate > 192000 ||
            align != channels * 2 ||
            data.getUint32(body + 8, Endian.little) != rate * align) {
          throw const FormatException('Invalid PCM layout.');
        }
      } else if (tag(cursor) == 'data') {
        if (start != null) throw const FormatException('Ambiguous WAV data.');
        start = body;
        count = size;
      }
      cursor = body + size + (size.isOdd ? 1 : 0);
    }
    if (cursor != bytes.length ||
        rate == null ||
        channels == null ||
        align == null ||
        start == null ||
        count == null ||
        count == 0 ||
        count % align != 0) {
      throw const FormatException('Incomplete WAV layout.');
    }
    final frames = count ~/ align;
    final peaks = List<double>.filled(math.min(96, frames), 0);
    for (var frame = 0; frame < frames; frame++) {
      final bin = frame * peaks.length ~/ frames;
      for (var channel = 0; channel < channels; channel++) {
        final sample = data
                .getInt16(start + frame * align + channel * 2, Endian.little)
                .abs() /
            32768;
        peaks[bin] = math.max(peaks[bin], sample);
      }
    }
    return StudioAudio._(bytes, hash as String, rate,
        Duration(microseconds: (frames * 1000000 / rate).round()), peaks);
  }
}

/// Checks the byte receipt and bounds image decoding; not scene correctness.
class StudioFrame {
  StudioFrame._(this.bytes, this.sha256Hex, this.width, this.height);
  final Uint8List bytes;
  final String sha256Hex;
  final int width, height;

  factory StudioFrame.fromJson(Map<String, dynamic> result) {
    final bytes = _checkedBytes(result['png_base64'], result['frame_sha256']);
    final data = ByteData.sublistView(bytes);
    if (bytes.length < 33 ||
        !listEquals(
            bytes.sublist(0, 8), const [137, 80, 78, 71, 13, 10, 26, 10]) ||
        data.getUint32(8) != 13 ||
        ascii.decode(bytes.sublist(12, 16), allowInvalid: true) != 'IHDR') {
      throw const FormatException('Expected a PNG frame.');
    }
    final width = data.getUint32(16), height = data.getUint32(20);
    if (width == 0 ||
        height == 0 ||
        width > 8192 ||
        height > 8192 ||
        width * height > 16 * 1024 * 1024) {
      throw const FormatException('Frame dimensions exceed preview limits.');
    }
    return StudioFrame._(
        bytes, result['frame_sha256'] as String, width, height);
  }
}
