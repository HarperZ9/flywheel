import 'dart:async';

import 'rowan_action_cue_player.dart';
import 'rowan_action_cue_recorded_player.dart';

/// Opening the app never initializes audio devices. First opted-in playback does.
class LazyRowanCuePlayer implements RowanActionCuePlayer {
  LazyRowanCuePlayer({RowanRecordedAssetCuePlayer Function()? create})
      : _create = create ?? RowanRecordedAssetCuePlayer.new;

  final RowanRecordedAssetCuePlayer Function() _create;
  final _completions = StreamController<void>.broadcast();
  RowanRecordedAssetCuePlayer? _player;
  StreamSubscription<void>? _subscription;
  bool _disposed = false;

  @override
  Stream<void> get completions => _completions.stream;

  @override
  Future<void> play(RowanActionCuePlayback playback) async {
    if (_disposed) throw StateError('Rowan audio is disposed');
    if (_player == null) {
      _player = _create();
      _subscription = _player!.completions.listen((_) {
        if (!_disposed) _completions.add(null);
      });
    }
    await _player!.play(playback);
  }

  @override
  Future<void> stop() async => _player?.stop();

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    await _subscription?.cancel();
    await _player?.dispose();
    await _completions.close();
  }
}
