import 'package:flutter/material.dart';

import '../navigation/app_route.dart';
import '../theme/flywheel_theme.dart';
import 'flywheel_nav.dart';
import 'start_task_prelude.dart';

class JourneyStartTaskEntry extends StatefulWidget {
  const JourneyStartTaskEntry({super.key});

  @override
  State<JourneyStartTaskEntry> createState() => _JourneyStartTaskEntryState();
}

class _JourneyStartTaskEntryState extends State<JourneyStartTaskEntry> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _startTask() {
    final text = _controller.text.trim();
    FlywheelNav.jump(context, DestinationId.chat,
        arg: text.isEmpty ? null : StartTaskHandoff(text));
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final nav = FlywheelNav.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      TextField(
        key: const Key('journey-start-task-input'),
        controller: _controller,
        minLines: 2,
        maxLines: 4,
        textInputAction: TextInputAction.newline,
        decoration: const InputDecoration(
          hintText: 'Example: find the receipt for a claim in this project…',
        ),
        onChanged: (_) => setState(() {}),
      ),
      const SizedBox(height: FwLayout.s2),
      Wrap(
        spacing: FwLayout.s2,
        runSpacing: FwLayout.s2,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          FilledButton(
            key: const Key('journey-start-task-primary'),
            onPressed: nav == null ? null : _startTask,
            style: FilledButton.styleFrom(minimumSize: const Size(44, 44)),
            child: const Text('Start a task'),
          ),
          Text(
            'Chat shows the selected model, access, cost if known, and '
            'workspace choice before anything runs.',
            style: fwMono(t, size: 11.5, color: t.inkFaint),
          ),
        ],
      ),
    ]);
  }
}
