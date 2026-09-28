import 'package:flutter/widgets.dart';

import '../assistant/lazy_rowan_cue_player.dart';
import '../assistant/rowan_action_cue_complete_ids.dart';
import '../assistant/rowan_action_cue_controller.dart';
import '../assistant/rowan_action_cue_event_binding.dart';
import '../assistant/rowan_action_cue_models.dart';
import '../assistant/rowan_action_cue_player.dart';
import '../controllers/live_screen_sharing.dart';
import '../controllers/rowan_walkthrough_operation_host.dart';

/// One cue lifecycle per application shell, independent of selected destination.
class ShellRowanCues {
  ShellRowanCues({
    required RowanWalkthroughOperationHost operationHost,
    required LiveScreenSharing screenSharing,
    RowanActionCuePlayer? player,
  })  : _sharing = screenSharing,
        _player = player ?? LazyRowanCuePlayer() {
    controller = RowanActionCueController(player: _player);
    binding = RowanActionCueEventBinding(
      operationHost: operationHost,
      controller: controller,
      screenSharing: RowanActionCueScreenSharingListenableSource(
        listenable: screenSharing,
        readSnapshot: readScreenSnapshot,
      ),
    );
  }

  final LiveScreenSharing _sharing;
  final RowanActionCuePlayer _player;
  late final RowanActionCueController controller;
  late final RowanActionCueEventBinding binding;
  String? _observedRunningSession;
  var _studioOpenSequence = 0;
  bool _disposed = false;

  static ShellRowanCues? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<ShellRowanCueScope>()?.cues;

  RowanActionCueDispatch get dispatch => controller.handle;

  Future<RowanActionCueDecision> studioOpened() => controller.handle(
        RowanActionCueEvent.fromStableEvent(
          kind: RowanCompleteActionCueEvents.studioOpen,
          eventRef: 'studio_open_${++_studioOpenSequence}',
        ),
      );

  RowanActionCueScreenSharingSnapshot readScreenSnapshot() {
    var origin = RowanActionCueObservationOrigin.observed;
    final session = _sharing.sessionId;
    if (session != null &&
        _sharing.feed.state.name == 'running' &&
        session != _observedRunningSession) {
      origin = switch (_sharing.sessionOrigin) {
        LiveScreenSessionOrigin.localStart =>
          RowanActionCueObservationOrigin.localStart,
        LiveScreenSessionOrigin.recovered =>
          RowanActionCueObservationOrigin.recovered,
        null => RowanActionCueObservationOrigin.observed,
      };
      _observedRunningSession = session;
    }
    return RowanActionCueScreenSharingSnapshot.fromLiveScreenSharing(
      _sharing,
      origin: origin,
    );
  }

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    await binding.dispose();
    await controller.dispose();
    final player = _player;
    if (player is LazyRowanCuePlayer) {
      await player.dispose();
    } else {
      await player.stop();
    }
  }
}

class ShellRowanCueScope extends InheritedWidget {
  const ShellRowanCueScope({
    super.key,
    required this.cues,
    required super.child,
  });

  final ShellRowanCues cues;

  @override
  bool updateShouldNotify(ShellRowanCueScope oldWidget) =>
      oldWidget.cues != cues;
}
