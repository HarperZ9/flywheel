import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/widgets/bulletin_media_player.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

void main() {
  late VideoPlayerPlatform originalPlatform;

  setUp(() => originalPlatform = VideoPlayerPlatform.instance);
  tearDown(() => VideoPlayerPlatform.instance = originalPlatform);

  testWidgets('player reports unsupported media when initialization errors',
      (tester) async {
    VideoPlayerPlatform.instance = _ErrorVideoPlatform();
    final file = File('${Directory.systemTemp.path}/bulletin-unsupported.bin')
      ..writeAsBytesSync([1, 2, 3]);
    addTearDown(() {
      if (file.existsSync()) file.deleteSync();
    });

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: BulletinMediaPlayer(file: file, kind: 'video')),
    ));
    await tester.pump();
    await tester.pump();

    expect(find.textContaining('Media preview failed or unsupported'),
        findsOneWidget);
    expect(find.textContaining('Loading native media preview'), findsNothing);
  });
}

final class _ErrorVideoPlatform extends VideoPlayerPlatform {
  final _events = StreamController<VideoEvent>();

  @override
  Future<void> init() async {}

  @override
  Future<int?> createWithOptions(VideoCreationOptions options) async {
    scheduleMicrotask(() => _events.addError(PlatformException(
          code: 'unsupported_codec',
          message: 'unsupported codec',
        )));
    return 1;
  }

  @override
  Stream<VideoEvent> videoEventsFor(int playerId) => _events.stream;

  @override
  Future<void> dispose(int playerId) => _events.close();

  @override
  Future<void> setLooping(int playerId, bool looping) async {}

  @override
  Future<void> play(int playerId) async {}

  @override
  Future<void> pause(int playerId) async {}

  @override
  Future<void> setVolume(int playerId, double volume) async {}

  @override
  Future<void> seekTo(int playerId, Duration position) async {}

  @override
  Future<void> setPlaybackSpeed(int playerId, double speed) async {}

  @override
  Future<Duration> getPosition(int playerId) async => Duration.zero;

  @override
  Widget buildViewWithOptions(VideoViewOptions options) => const SizedBox();
}
