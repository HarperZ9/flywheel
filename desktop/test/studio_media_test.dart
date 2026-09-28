import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/studio_media.dart';

Uint8List studioTestWav() {
  final bytes = Uint8List(52);
  final data = ByteData.sublistView(bytes);
  void tag(int offset, String value) =>
      bytes.setRange(offset, offset + 4, ascii.encode(value));
  tag(0, 'RIFF');
  data.setUint32(4, 44, Endian.little);
  tag(8, 'WAVE');
  tag(12, 'fmt ');
  data.setUint32(16, 16, Endian.little);
  data.setUint16(20, 1, Endian.little);
  data.setUint16(22, 1, Endian.little);
  data.setUint32(24, 8000, Endian.little);
  data.setUint32(28, 16000, Endian.little);
  data.setUint16(32, 2, Endian.little);
  data.setUint16(34, 16, Endian.little);
  tag(36, 'data');
  data.setUint32(40, 8, Endian.little);
  for (var i = 0; i < 4; i++) {
    data.setInt16(44 + i * 2, [0, 16384, -32768, 8192][i], Endian.little);
  }
  return bytes;
}

Map<String, dynamic> studioTestResult(Uint8List bytes) => {
      'wav_b64': base64Encode(bytes),
      'receipt': {'wav_sha256': sha256.convert(bytes).toString()},
    };

void main() {
  test('waveform comes from checked PCM bytes and cannot mutate afterwards',
      () {
    final bytes = studioTestWav();
    final audio = StudioAudio.fromResult(studioTestResult(bytes));
    expect(audio.sampleRate, 8000);
    expect(audio.duration.inMicroseconds, 500);
    expect(audio.peaks, [0, 0.5, 1, 0.25]);
    expect(() => audio.bytes[0] = 0, throwsUnsupportedError);
    expect(() => audio.peaks[0] = 1, throwsUnsupportedError);
  });

  test('changed audio is rejected even if it remains a playable WAV', () {
    final bytes = studioTestWav();
    final result = studioTestResult(bytes);
    bytes[48] = 5;
    result['wav_b64'] = base64Encode(bytes);
    expect(() => StudioAudio.fromResult(result), throwsFormatException);
  });

  test('hash agreement does not make malformed WAVs valid', () {
    for (final mutate in <void Function(ByteData)>[
      (b) => b.setUint32(40, 100, Endian.little),
      (b) => b.setUint16(34, 8, Endian.little),
      (b) => b.setUint16(22, 0, Endian.little),
      (b) => b.setUint32(24, 0, Endian.little),
      (b) => b.setUint32(4, 0, Endian.little),
      (b) => b.setUint32(28, 1, Endian.little),
    ]) {
      final bytes = studioTestWav();
      mutate(ByteData.sublistView(bytes));
      expect(() => StudioAudio.fromResult(studioTestResult(bytes)),
          throwsFormatException);
    }
  });

  test('frame checks the PNG bytes against the full frame hash', () {
    final png = base64Decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=');
    final result = <String, dynamic>{
      'png_base64': base64Encode(png),
      'frame_sha256': sha256.convert(png).toString(),
      'frame': 0,
    };
    final frame = StudioFrame.fromJson(result);
    expect(frame.bytes, png);
    expect(frame.width, 1);
    expect(frame.height, 1);
    result['frame_sha256'] = 'abc';
    expect(() => StudioFrame.fromJson(result), throwsFormatException);
    result['png_base64'] = base64Encode(studioTestWav());
    result['frame_sha256'] = sha256.convert(studioTestWav()).toString();
    expect(() => StudioFrame.fromJson(result), throwsFormatException);
  });
}
