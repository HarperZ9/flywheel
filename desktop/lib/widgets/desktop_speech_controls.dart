import 'package:flutter/material.dart';
import '../assistant/desktop_speech_controller.dart';
import '../theme/flywheel_theme.dart';

class DesktopSpeechControls extends StatelessWidget {
  const DesktopSpeechControls({super.key, required this.controller});
  final DesktopSpeechController controller;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final label = !controller.supported
            ? 'Unavailable'
            : !controller.enabled
                ? 'Speak replies'
                : controller.muted
                    ? 'Muted'
                    : controller.speaking
                        ? 'Reading'
                        : 'Ready';
        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(mainAxisSize: MainAxisSize.min, children: [
              Semantics(
                  label: 'Speak replies',
                  child: SizedBox(
                      width: 44,
                      height: 32,
                      child: FittedBox(
                          child: Switch.adaptive(
                              key: const Key('desktop-speech-enabled'),
                              value: controller.enabled,
                              onChanged: controller.supported
                                  ? controller.setEnabled
                                  : null)))),
              Tooltip(
                  message: controller.status,
                  child: Semantics(
                      liveRegion: true,
                      label: controller.status,
                      child: SizedBox(
                          width: controller.enabled ? 40 : 80,
                          child: FittedBox(
                              fit: BoxFit.scaleDown,
                              alignment: Alignment.centerLeft,
                              child: Text(label,
                                  style: TextStyle(
                                      color: context.fw.inkMuted,
                                      fontSize: 12)))))),
              if (controller.enabled) ...[
                IconButton(
                    key: const Key('desktop-speech-mute'),
                    constraints:
                        const BoxConstraints(minWidth: 32, minHeight: 32),
                    visualDensity: VisualDensity.compact,
                    padding: const EdgeInsets.all(FwLayout.s1),
                    tooltip:
                        controller.muted ? 'Unmute replies' : 'Mute replies',
                    onPressed: () => controller.setMuted(!controller.muted),
                    icon: Icon(
                        controller.muted ? Icons.volume_off : Icons.volume_up,
                        size: 18)),
                IconButton(
                    key: const Key('desktop-speech-stop'),
                    constraints:
                        const BoxConstraints(minWidth: 32, minHeight: 32),
                    visualDensity: VisualDensity.compact,
                    padding: const EdgeInsets.all(FwLayout.s1),
                    tooltip: 'Stop speech',
                    onPressed: controller.interrupt,
                    icon: const Icon(Icons.stop_rounded, size: 18)),
              ],
            ]),
            if (controller.problem case final explanation?)
              SizedBox(
                  width: 240,
                  child: Semantics(
                      liveRegion: true,
                      child: Text(explanation,
                          key: const Key('desktop-speech-status'),
                          style: TextStyle(color: context.fw.inkMuted)))),
          ],
        );
      });
}
