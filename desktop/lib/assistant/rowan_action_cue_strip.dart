import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'rowan_action_cue_caption.dart';

/// Keeps the latest spoken cue readable without opening voice settings.
/// Dismissing this view does not alter the controller's caption or receipt.
class RowanActionCueStrip extends StatefulWidget {
  const RowanActionCueStrip({super.key, required this.captions});

  final ValueListenable<RowanActionCueCaptionState?> captions;

  @override
  State<RowanActionCueStrip> createState() => _RowanActionCueStripState();
}

class _RowanActionCueStripState extends State<RowanActionCueStrip> {
  (String?, String, String)? _dismissed;

  @override
  Widget build(BuildContext context) =>
      ValueListenableBuilder<RowanActionCueCaptionState?>(
        valueListenable: widget.captions,
        builder: (context, caption, _) {
          if (caption == null) return const SizedBox.shrink();
          final identity = (
            caption.eventRef,
            caption.captionSha256,
            caption.playbackProvenanceSha256,
          );
          if (_dismissed == identity) return const SizedBox.shrink();
          final t = context.fw;
          return Container(
            key: const Key('rowan-cue-caption-strip'),
            decoration: BoxDecoration(
              color: t.ground2,
              border: Border(top: BorderSide(color: t.line)),
            ),
            padding: const EdgeInsets.only(left: 16, top: 4, bottom: 4),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxHeight: 144),
                    child: SingleChildScrollView(
                      child: Semantics(
                        container: true,
                        liveRegion: true,
                        child: Text(caption.caption,
                            style: Theme.of(context).textTheme.bodyMedium),
                      ),
                    ),
                  ),
                ),
                IconButton(
                  tooltip: 'Dismiss Rowan caption',
                  icon: const Icon(Icons.close, size: 18),
                  onPressed: () => setState(() => _dismissed = identity),
                ),
              ],
            ),
          );
        },
      );
}
