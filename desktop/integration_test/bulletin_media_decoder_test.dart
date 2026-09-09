import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:video_player/video_player.dart';

const _definedReceipt = String.fromEnvironment('BULLETIN_DECODER_RECEIPT');
const _definedRunId = String.fromEnvironment('BULLETIN_DECODER_RUN_ID');
const _definedMp4 = String.fromEnvironment('BULLETIN_DECODER_MP4');
const _definedUnsupportedMp4 =
    String.fromEnvironment('BULLETIN_DECODER_UNSUPPORTED_MP4');

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
      'Windows decoder plays WAV and H.264 MP4, rejects corrupt MP4 and unsupported MP4 codec',
      (tester) async {
    if (!Platform.isWindows) {
      markTestSkipped('Windows native decoder proof is Windows-only.');
      return;
    }
    final runId = _configured('BULLETIN_DECODER_RUN_ID', _definedRunId);
    final receipt = _configured('BULLETIN_DECODER_RECEIPT', _definedReceipt);
    final mp4 = File(_configured('BULLETIN_DECODER_MP4', _definedMp4));
    final unsupportedMp4 = File(_configured(
        'BULLETIN_DECODER_UNSUPPORTED_MP4', _definedUnsupportedMp4));

    expect(runId, isNotEmpty,
        reason: 'runner must pass a fresh BULLETIN_DECODER_RUN_ID');
    expect(receipt, isNotEmpty,
        reason: 'runner must pass BULLETIN_DECODER_RECEIPT');
    expect(mp4.existsSync(), isTrue,
        reason: 'run tool/run_bulletin_media_decoder_smoke.ps1 first');
    expect(unsupportedMp4.existsSync(), isTrue,
        reason: 'run tool/run_bulletin_media_decoder_smoke.ps1 first');

    final dir = Directory.systemTemp.createTempSync('bulletin-decoder-');
    addTearDown(() {
      if (dir.existsSync()) dir.deleteSync(recursive: true);
    });
    final wav = File('${dir.path}${Platform.pathSeparator}tone.wav')
      ..writeAsBytesSync(_wavTone(seconds: 2));
    final corrupt = File('${dir.path}${Platform.pathSeparator}corrupt.mp4')
      ..writeAsBytesSync(List<int>.filled(512, 0));

    final fixtures = {
      'h264_mp4': _fixtureIdentity(mp4),
      'unsupported_h264_high10_mp4': _fixtureIdentity(unsupportedMp4),
    };
    final wavProof = await _probePlayable(tester, wav);
    final mp4Proof = await _probePlayable(tester, mp4);
    final corruptProof = await _probeRejected(tester, corrupt);
    final unsupportedProof = await _probeRejected(tester, unsupportedMp4);
    final cases = {
      'wav': wavProof,
      'h264_mp4': mp4Proof,
      'corrupt_mp4': corruptProof,
      'unsupported_h264_high10_mp4': unsupportedProof,
    };

    void writeReceipt({required bool complete}) {
      File(receipt)
        ..parent.createSync(recursive: true)
        ..writeAsStringSync(jsonEncode({
          'schema': 'flywheel.bulletin-media-windows-decoder-proof/v2',
          'run_id': runId,
          'complete': complete,
          'fixtures': fixtures,
          'cases': cases,
        }));
    }

    writeReceipt(complete: false);

    expect(wavProof['initialized'], isTrue);
    expect(wavProof['position_ms'] as int, greaterThan(0));
    expect(mp4Proof['initialized'], isTrue);
    expect(mp4Proof['position_ms'] as int, greaterThan(0));
    expect(mp4Proof['frame_width'] as double, greaterThan(0));
    expect(mp4Proof['frame_height'] as double, greaterThan(0));
    expect(corruptProof['negative'], isTrue);
    expect(unsupportedProof['negative'], isTrue);
    expect(
        unsupportedProof['initialize_threw'] == true ||
            unsupportedProof['has_error'] == true,
        isTrue);
    writeReceipt(complete: true);
  });
}

Future<Map<String, Object?>> _probePlayable(
    WidgetTester tester, File file) async {
  final controller = VideoPlayerController.file(file);
  addTearDown(controller.dispose);
  await tester.runAsync(() async {
    await controller.initialize().timeout(const Duration(seconds: 20));
    await controller.play().timeout(const Duration(seconds: 5));
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    await controller.pause().timeout(const Duration(seconds: 5));
  });
  return {
    'path': file.path,
    'sha256': _sha256(file),
    'bytes': file.lengthSync(),
    'initialized': controller.value.isInitialized,
    'has_error': controller.value.hasError,
    'duration_ms': controller.value.duration.inMilliseconds,
    'position_ms': controller.value.position.inMilliseconds,
    'frame_width': controller.value.size.width,
    'frame_height': controller.value.size.height,
  };
}

Future<Map<String, Object?>> _probeRejected(
    WidgetTester tester, File file) async {
  final controller = VideoPlayerController.file(file);
  addTearDown(controller.dispose);
  var threw = false;
  await tester.runAsync(() async {
    try {
      await controller.initialize().timeout(const Duration(seconds: 20));
      await controller.play().timeout(const Duration(seconds: 5));
      await Future<void>.delayed(const Duration(milliseconds: 700));
      await controller.pause().timeout(const Duration(seconds: 5));
    } on Object {
      threw = true;
    }
  });
  final negative = threw ||
      controller.value.hasError ||
      controller.value.duration <= Duration.zero ||
      controller.value.position <= Duration.zero;
  return {
    'path': file.path,
    'sha256': _sha256(file),
    'bytes': file.lengthSync(),
    'initialize_threw': threw,
    'initialized': controller.value.isInitialized,
    'has_error': controller.value.hasError,
    'duration_ms': controller.value.duration.inMilliseconds,
    'position_ms': controller.value.position.inMilliseconds,
    'frame_width': controller.value.size.width,
    'frame_height': controller.value.size.height,
    'negative': negative,
  };
}

Map<String, Object?> _fixtureIdentity(File file) => {
      'path': file.path,
      'sha256': _sha256(file),
      'bytes': file.lengthSync(),
    };

String _sha256(File file) => sha256.convert(file.readAsBytesSync()).toString();

String _configured(String envName, String defined) =>
    defined.isNotEmpty ? defined : Platform.environment[envName] ?? '';

List<int> _wavTone({required int seconds}) {
  const sampleRate = 44100;
  const channels = 1;
  const bitsPerSample = 16;
  final samples = sampleRate * seconds;
  final dataBytes = samples * channels * bitsPerSample ~/ 8;
  final out = BytesBuilder();
  void ascii(String value) => out.add(value.codeUnits);
  void u16(int value) => out.add([value & 0xff, (value >> 8) & 0xff]);
  void u32(int value) => out.add([
        value & 0xff,
        (value >> 8) & 0xff,
        (value >> 16) & 0xff,
        (value >> 24) & 0xff,
      ]);

  ascii('RIFF');
  u32(36 + dataBytes);
  ascii('WAVEfmt ');
  u32(16);
  u16(1);
  u16(channels);
  u32(sampleRate);
  u32(sampleRate * channels * bitsPerSample ~/ 8);
  u16(channels * bitsPerSample ~/ 8);
  u16(bitsPerSample);
  ascii('data');
  u32(dataBytes);
  for (var i = 0; i < samples; i++) {
    final sample =
        (math.sin(2 * math.pi * 440 * i / sampleRate) * 16000).round();
    u16(sample & 0xffff);
  }
  return out.takeBytes();
}
