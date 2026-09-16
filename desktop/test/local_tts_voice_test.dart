import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/assistant/local_tts_voice.dart';

const job1 = 'tts_11111111111111111111111111111111';
const job2 = 'tts_22222222222222222222222222222222';

void main() {
  test('rejects non-loopback service URLs', () {
    expect(
      () => LocalTtsVoiceOutput(
        token: 'test-token',
        baseUrl: 'https://tts.example.test',
      ),
      throwsArgumentError,
    );
  });

  test('submits text with bearer auth and hands off completed audio', () async {
    final calls = <http.Request>[];
    LocalTtsSpeakResult? handedOff;
    final client = MockClient((request) async {
      calls.add(request);
      expect(request.followRedirects, isFalse);
      expect(request.maxRedirects, 0);
      expect(request.headers['Authorization'], 'Bearer test-token');
      if (request.url.path == '/v1/speak') {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['text'], 'Hello Rowan.');
        expect(body['profile'], 'rowan-draft-adjustable-20260915');
        expect(body['wait'], isTrue);
        return http.Response(
          jsonEncode({
            'job_id': job1,
            'state': 'completed',
            'audio_path': r'C:\tmp\audio.wav',
            'manifest_path': r'C:\tmp\manifest.json',
          }),
          200,
        );
      }
      fail('unexpected path ${request.url.path}');
    });
    final voice = LocalTtsVoiceOutput(
      token: 'test-token',
      httpClient: client,
      onAudioReady: (result) => handedOff = result,
    );

    await voice.speak('Hello Rowan.');

    expect(calls, hasLength(1));
    expect(voice.lastResult?.jobId, job1);
    expect(voice.lastResult?.state, 'completed');
    expect(voice.lastResult?.audioPath, r'C:\tmp\audio.wav');
    expect(handedOff?.jobId, job1);
  });

  test('polls exact issued job route when wait returns a queued job', () async {
    var reads = 0;
    final client = MockClient((request) async {
      expect(request.followRedirects, isFalse);
      if (request.url.path == '/v1/speak') {
        return http.Response(
          jsonEncode(
              {'job_id': job1, 'state': 'queued', 'job_url': '/v1/jobs/$job1'}),
          202,
        );
      }
      reads++;
      expect(request.url.path, '/v1/jobs/$job1');
      return http.Response(
        jsonEncode({
          'job_id': job1,
          'state': 'completed',
          'audio_path': r'C:\tmp\done.wav',
        }),
        200,
      );
    });
    final voice = LocalTtsVoiceOutput(
      token: 'test-token',
      httpClient: client,
      pollInterval: Duration.zero,
    );

    final result = await voice.synthesize('Done soon.');

    expect(reads, 1);
    expect(result.audioPath, r'C:\tmp\done.wav');
  });

  test('rejects external advertised job URL before polling', () async {
    final calls = <http.Request>[];
    final client = MockClient((request) async {
      calls.add(request);
      return http.Response(
        jsonEncode({
          'job_id': job1,
          'state': 'queued',
          'job_url': '//external.example/v1/jobs/$job1'
        }),
        202,
      );
    });
    final voice = LocalTtsVoiceOutput(token: 'test-token', httpClient: client);

    await expectLater(
      voice.synthesize('Queued.'),
      throwsA(isA<FormatException>()),
    );
    expect(calls, hasLength(1));
  });

  test('rejects mismatched job id while polling', () async {
    final client = MockClient((request) async {
      if (request.url.path == '/v1/speak') {
        return http.Response(
          jsonEncode(
              {'job_id': job1, 'state': 'queued', 'job_url': '/v1/jobs/$job1'}),
          202,
        );
      }
      return http.Response(
        jsonEncode({'job_id': job2, 'state': 'completed'}),
        200,
      );
    });
    final voice = LocalTtsVoiceOutput(
      token: 'test-token',
      httpClient: client,
      pollInterval: Duration.zero,
    );

    await expectLater(
      voice.synthesize('Queued.'),
      throwsA(isA<FormatException>()),
    );
  });

  test('rejects oversized response body', () async {
    final client = MockClient((_) async {
      return http.Response(
        List.filled(LocalTtsVoiceOutput.maxResponseBytes + 1, 'x').join(),
        200,
      );
    });
    final voice = LocalTtsVoiceOutput(token: 'test-token', httpClient: client);

    await expectLater(
      voice.synthesize('Hello.'),
      throwsA(isA<FormatException>()),
    );
  });

  test('can cancel the last submitted job by exact route', () async {
    final paths = <String>[];
    final client = MockClient((request) async {
      paths.add(request.url.path);
      expect(request.followRedirects, isFalse);
      if (request.url.path == '/v1/speak') {
        return http.Response(
          jsonEncode(
              {'job_id': job1, 'state': 'queued', 'job_url': '/v1/jobs/$job1'}),
          202,
        );
      }
      if (request.url.path == '/v1/jobs/$job1/cancel') {
        return http.Response(
          jsonEncode({'job_id': job1, 'state': 'cancelled'}),
          200,
        );
      }
      return http.Response(
        jsonEncode({'job_id': job1, 'state': 'queued'}),
        200,
      );
    });
    final voice = LocalTtsVoiceOutput(
      token: 'test-token',
      httpClient: client,
      waitForAudio: false,
    );

    final submitted = await voice.synthesize('Queued.');
    voice.lastResult = submitted;
    final cancelled = await voice.cancelLast();

    expect(cancelled.state, 'cancelled');
    expect(paths, contains('/v1/jobs/$job1/cancel'));
  });

  test('rejects oversized text before sending', () async {
    final voice = LocalTtsVoiceOutput(
      token: 'test-token',
      httpClient: MockClient((_) async => throw StateError('not called')),
    );

    await expectLater(
      voice.synthesize(
        List.filled(LocalTtsVoiceOutput.maxTextChars + 1, 'x').join(),
      ),
      throwsArgumentError,
    );
  });

  test('rejects work after close', () async {
    final voice = LocalTtsVoiceOutput(
      token: 'test-token',
      httpClient: MockClient((_) async => throw StateError('not called')),
    );

    voice.close();

    await expectLater(voice.synthesize('Hello.'), throwsStateError);
  });
}
