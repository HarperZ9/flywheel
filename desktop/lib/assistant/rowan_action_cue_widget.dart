import 'package:flutter/material.dart';

import 'rowan_action_cue_caption.dart';
import 'rowan_action_cue_controller.dart';

class RowanActionCueControls extends StatefulWidget {
  const RowanActionCueControls({
    super.key,
    required this.controller,
    this.title = 'Rowan action cues',
  });

  final RowanActionCueController controller;
  final String title;

  @override
  State<RowanActionCueControls> createState() => _RowanActionCueControlsState();
}

class _RowanActionCueControlsState extends State<RowanActionCueControls> {
  RowanActionCueController get _controller => widget.controller;

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(widget.title,
                  style: Theme.of(context).textTheme.titleMedium),
              SwitchListTile(
                key: const Key('rowan-action-cues-enabled'),
                contentPadding: EdgeInsets.zero,
                title: const Text('Play recorded cues'),
                subtitle: const Text('Only for new live events after opt-in.'),
                value: _controller.settings.enabled,
                onChanged: (value) => setState(() {
                  _controller.setEnabled(value);
                }),
              ),
              SwitchListTile(
                key: const Key('rowan-action-cues-muted'),
                contentPadding: EdgeInsets.zero,
                title: const Text('Mute cues'),
                subtitle: const Text('Captions remain available for review.'),
                value: _controller.settings.muted,
                onChanged: (value) => setState(() {
                  _controller.setMuted(value);
                }),
              ),
              ValueListenableBuilder<RowanActionCueCaptionState?>(
                valueListenable: _controller.captions,
                builder: (context, caption, _) =>
                    _CaptionView(caption: caption),
              ),
              ValueListenableBuilder<RowanActionCueCancellationState>(
                valueListenable: _controller.cancellation,
                builder: (context, cancellation, _) =>
                    _CancellationView(cancellation: cancellation),
              ),
            ],
          ),
        ),
      );
}

class _CaptionView extends StatelessWidget {
  const _CaptionView({required this.caption});

  final RowanActionCueCaptionState? caption;

  @override
  Widget build(BuildContext context) {
    final current = caption;
    if (current == null) {
      return const Text('No recorded cue has played in this view.');
    }
    return Semantics(
      liveRegion: true,
      label: current.recordedReplay
          ? 'Recorded replay caption'
          : 'Recorded cue caption',
      child: Text(current.caption),
    );
  }
}

class _CancellationView extends StatelessWidget {
  const _CancellationView({required this.cancellation});

  final RowanActionCueCancellationState cancellation;

  @override
  Widget build(BuildContext context) {
    final message = cancellation.message;
    if (message == null ||
        cancellation.status == RowanActionCueCancellationStatus.stopped) {
      return const SizedBox.shrink();
    }
    return Semantics(
      liveRegion: true,
      label: 'Rowan action cue cancellation state',
      child: Text(message),
    );
  }
}
