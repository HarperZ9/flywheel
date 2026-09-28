import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/studio_media.dart';
import 'package:flywheel_desktop/services/studio_audio_player.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/sound_panel.dart';

import 'studio_audio_test_fixtures.dart';

void main() {
  testWidgets('valid composed audio is loaded without autoplay',
      (tester) async {
    final playback = FakeStudioAudioPlayback();
    final client = _client([
      http.Response(jsonEncode(studioAudioResult(studioTestWav())), 200),
    ]);

    await tester.pumpWidget(_host(SoundPanel(
      client: client,
      playback: playback,
    )));
    await tester.tap(find.text('Compose'));
    await tester.pumpAndSettle();

    expect(playback.loaded, hasLength(1));
    expect(playback.playCalls, 0);
    expect(find.text('Play'), findsOneWidget);
    expect(find.text('Save WAV'), findsOneWidget);
  });

  testWidgets('corrupted audio is rejected before player load', (tester) async {
    final playback = FakeStudioAudioPlayback();
    final bytes = studioTestWav();
    final result = studioAudioResult(bytes);
    bytes[48] = 5;
    result['wav_b64'] = base64Encode(bytes);

    await tester.pumpWidget(_host(SoundPanel(
      client: _client([http.Response(jsonEncode(result), 200)]),
      playback: playback,
    )));
    await tester.tap(find.text('Compose'));
    await tester.pumpAndSettle();

    expect(playback.loaded, isEmpty);
    expect(find.textContaining('Media bytes do not match'), findsOneWidget);
    expect(find.text('Play'), findsNothing);
  });

  testWidgets('new compose clears existing playback before response returns',
      (tester) async {
    final playback = FakeStudioAudioPlayback();
    final pending = Completer<http.Response>();
    final client = GatewayClient(
      httpClient: MockClient((request) {
        if (playback.loaded.isEmpty) {
          return Future.value(http.Response(
              jsonEncode(studioAudioResult(studioTestWav())), 200));
        }
        return pending.future;
      }),
    );

    await tester.pumpWidget(_host(SoundPanel(
      client: client,
      playback: playback,
    )));
    await tester.tap(find.text('Compose'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Compose'));
    await tester.pump();

    expect(playback.clearCalls, 1);
    pending.complete(http.Response(
        jsonEncode(studioAudioResult(studioTestWav(samples: const [1, 2]))),
        200));
  });

  testWidgets('changing client invalidates current playback', (tester) async {
    final playback = FakeStudioAudioPlayback();
    await tester.pumpWidget(_host(SoundPanel(
      client: _client([
        http.Response(jsonEncode(studioAudioResult(studioTestWav())), 200),
      ]),
      playback: playback,
    )));
    await tester.tap(find.text('Compose'));
    await tester.pumpAndSettle();

    await tester.pumpWidget(_host(SoundPanel(
      client: _client([]),
      playback: playback,
    )));

    expect(playback.clearCalls, 1);
    expect(find.text('Play'), findsNothing);
  });
}

GatewayClient _client(List<http.Response> responses) {
  var index = 0;
  return GatewayClient(
    httpClient: MockClient((request) async => responses[index++]),
  );
}

Widget _host(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

class FakeStudioAudioPlayback extends ChangeNotifier
    implements StudioAudioPlayback {
  final loaded = <StudioAudio>[];
  var playCalls = 0;
  var clearCalls = 0;
  var _state = const StudioAudioPlaybackState();

  @override
  StudioAudioPlaybackState get state => _state;

  @override
  Future<void> load(StudioAudio audio) async {
    loaded.add(audio);
    _state = StudioAudioPlaybackState(
      audio: audio,
      status: StudioAudioPlaybackStatus.ready,
    );
    notifyListeners();
  }

  @override
  Future<void> clear() async {
    clearCalls++;
    _state = const StudioAudioPlaybackState();
    notifyListeners();
  }

  @override
  Future<void> pause() async {}

  @override
  Future<void> play() async {
    playCalls++;
  }

  @override
  Future<void> seek(Duration position) async {}

  @override
  Future<void> stop() async {}

  @override
  @override
  Future<void> close() async {}
}
