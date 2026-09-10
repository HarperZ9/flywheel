import 'dart:convert';

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

/// Execution status is reported by the tool, independently of answer checks.
String agentExecutionStatus(Map<String, dynamic> event) =>
    switch (event['ok']) {
      true => 'Execution succeeded',
      false => 'Execution failed',
      _ => 'Execution status unavailable',
    };

/// Inspect the event already admitted to the timeline. This does not fetch,
/// persist, or reinterpret source data or replace the run's integrity checks.
class AgentEventDetail extends StatelessWidget {
  final Map<String, dynamic> event;
  const AgentEventDetail({super.key, required this.event});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final requiredFields = switch (event['type']) {
      'tool_call' => ['name', 'args'],
      'tool_result' => ['name', 'ok', 'output'],
      _ => ['type'],
    };
    return Dialog(
      insetPadding: const EdgeInsets.all(16),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760, maxHeight: 720),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Expanded(child: Text('Full recorded payload')),
                IconButton(
                  tooltip: 'Close event details',
                  onPressed: () => Navigator.of(context).pop(),
                  icon: const Icon(Icons.close),
                ),
              ]),
              if (event['type'] == 'tool_result')
                Text(agentExecutionStatus(event)),
              const Text('Recorded content does not establish factual accuracy '
                  'or receipt integrity.'),
              const SizedBox(height: 12),
              Flexible(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      for (final name in requiredFields)
                        if (!event.containsKey(name))
                          Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: Text('$name: not recorded'),
                          ),
                      for (final entry in event.entries)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('${entry.key} (${_type(entry.value)})',
                                  style: fwMono(t, size: 12)),
                              const SizedBox(height: 4),
                              SelectableText(_content(entry.value),
                                  style: fwMono(t, size: 12)
                                      .copyWith(height: 1.5)),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  static String _type(Object? value) => switch (value) {
        null => 'null',
        String() => 'string',
        bool() => 'boolean',
        num() => 'number',
        Map() => 'object',
        List() => 'array',
        _ => 'unsupported',
      };

  static String _content(Object? value) {
    // Strings remain verbatim, including text that happens to contain JSON.
    if (value is String) return value;
    try {
      return const JsonEncoder.withIndent('  ').convert(value);
    } on JsonUnsupportedObjectError {
      return 'Content unavailable: unsupported event value.';
    }
  }
}
