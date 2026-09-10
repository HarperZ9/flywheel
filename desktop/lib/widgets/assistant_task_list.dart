import 'package:flutter/material.dart';
import '../assistant/assistant_task_controller.dart';
import '../models/assistant_task.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class AssistantTaskList extends StatelessWidget {
  const AssistantTaskList({super.key, required this.controller});
  final AssistantTaskController controller;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Expanded(child: Text('Gateway tasks')),
            IconButton(
              tooltip: 'Refresh gateway tasks',
              onPressed: controller.loading ? null : controller.recover,
              icon: const Icon(Icons.refresh),
            ),
          ]),
          const Text('Recent work from this connected gateway. '
              'These tasks may have been started elsewhere.'),
          if (controller.unavailable)
            const HonestNull('Gateway tasks could not be read. '
                'Check the connection and refresh; do not resubmit.'),
          if (controller.loading) const LinearProgressIndicator(),
          if (!controller.loading &&
              !controller.unavailable &&
              controller.tasks.isEmpty)
            const HonestNull('No recent gateway tasks were returned.'),
          for (final task in controller.tasks)
            Padding(
              padding: const EdgeInsets.only(top: FwLayout.s2),
              child: _task(context, task),
            ),
        ],
      );

  Widget _task(BuildContext context, AssistantTask task) => HairlineCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text(task.label)),
            IconButton(
              key: ValueKey('assistant-task-refresh-${task.runId}'),
              tooltip: 'Refresh task ${task.runId}',
              onPressed: () => controller.refresh(task.runId),
              icon: const Icon(Icons.refresh),
            ),
          ]),
          SelectableText('run ${task.runId}',
              style: fwMono(context.fw, size: 11)),
          if (task.steps != null) Text('${task.steps} steps reported'),
          if (task.readFailed)
            Text(task.state == AssistantTaskState.completed
                ? 'Execution finished, but its result and receipts could not be read. Refresh to retry the read.'
                : 'Current task state could not be confirmed. Refresh to retry the read.'),
          if (task.state == AssistantTaskState.completed) ...[
            Text(task.evidenceLabel),
            const Text(
                'Answer accuracy is not established by execution or receipt integrity.'),
          ],
          if (task.checkpoint != null)
            SelectableText('Checkpoint: ${task.checkpoint}',
                style: fwMono(context.fw, size: 10)),
        ]),
      );
}
