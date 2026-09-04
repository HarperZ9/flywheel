// bench_task_editor.dart -- the task rows of a private benchmark.
//
// The tasks are the operator's own, and that is the whole point: a task set
// nobody trained on is the only one whose pass rate means anything. Each row
// is a prompt and the shell command that judges the answer. The gate is a
// real subprocess, so an empty gate is not a task and the form says so.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class BenchTask {
  final TextEditingController id, prompt, gate;
  BenchTask()
      : id = TextEditingController(),
        prompt = TextEditingController(),
        gate = TextEditingController();

  void dispose() {
    id.dispose();
    prompt.dispose();
    gate.dispose();
  }

  bool get complete =>
      id.text.trim().isNotEmpty &&
      prompt.text.trim().isNotEmpty &&
      gate.text.trim().isNotEmpty;

  Map<String, dynamic> toJson() => {
        'task_id': id.text.trim(),
        'prompt': prompt.text.trim(),
        'gate_cmd': gate.text.trim(),
      };
}

class BenchTaskEditor extends StatelessWidget {
  final List<BenchTask> tasks;
  final bool enabled;
  final VoidCallback onAdd;
  final void Function(int index) onRemove;
  final VoidCallback onChanged;

  const BenchTaskEditor({
    super.key,
    required this.tasks,
    required this.enabled,
    required this.onAdd,
    required this.onRemove,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('tasks · yours, so no one trained on them'),
        const SizedBox(height: FwLayout.s2),
        if (tasks.isEmpty)
          const HonestNull(
              'No tasks yet. A benchmark with no tasks measures nothing.'),
        for (var i = 0; i < tasks.length; i++) _row(t, i),
        const SizedBox(height: FwLayout.s2),
        OutlinedButton(
            onPressed: enabled ? onAdd : null, child: const Text('Add task')),
      ],
    );
  }

  Widget _row(FwTokens t, int i) {
    final task = tasks[i];
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s3),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            SizedBox(
              width: 160,
              child: _field(t, task.id, 'task id', 'sort-stability'),
            ),
            const SizedBox(width: FwLayout.s3),
            Expanded(child: _field(t, task.gate, 'gate command', 'pytest -q')),
            IconButton(
              tooltip: 'Remove',
              onPressed: enabled ? () => onRemove(i) : null,
              icon: const Icon(Icons.close_rounded, size: 16),
            ),
          ]),
          const SizedBox(height: 4),
          _field(t, task.prompt, 'prompt', 'what the endpoint is asked to do',
              lines: 2),
        ],
      ),
    );
  }

  Widget _field(FwTokens t, TextEditingController c, String label, String hint,
          {int lines = 1}) =>
      TextField(
        controller: c,
        enabled: enabled,
        maxLines: lines,
        onChanged: (_) => onChanged(),
        style: fwMono(t, size: 11.5, color: t.ink),
        decoration: InputDecoration(
            isDense: true, labelText: label, hintText: hint),
      );
}
