// lane_result_view.dart - one lane tool's answer, as rows with the raw JSON
// folded underneath.
//
// A lane tool answers any JSON value. The top-level fields become one row
// each, a nested value shows its size, and the whole answer stays one tap
// away as indented JSON. Nothing is reinterpreted: the rows are the answer.

import 'dart:convert';

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

const _maxValueChars = 160;

/// The rows for [result]: (label, value) pairs in the answer's own order.
List<(String, String)> laneResultRows(Object? result) {
  if (result is Map) {
    return [for (final e in result.entries) ('${e.key}', _short(e.value))];
  }
  if (result is List) return [('items', '${result.length}')];
  return [('result', _short(result))];
}

String _short(Object? value) {
  final text = switch (value) {
    null => 'null',
    String s => s,
    num n => '$n',
    bool b => '$b',
    List l => '${l.length} items',
    Map m => '${m.length} fields',
    _ => '$value',
  };
  return text.length <= _maxValueChars
      ? text
      : '${text.substring(0, _maxValueChars)}...';
}

class LaneResultView extends StatelessWidget {
  final String tool;
  final Object? result;
  const LaneResultView({super.key, required this.tool, required this.result});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final rows = laneResultRows(result);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        const VerdictPill('answered', status: 'verified'),
        const SizedBox(width: FwLayout.s2),
        Expanded(
            child: Text(tool, style: fwMono(t, size: 11.5, color: t.inkSoft))),
      ]),
      const SizedBox(height: FwLayout.s2),
      for (final (label, value) in rows)
        Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SizedBox(
              width: 140,
              child: Text(label,
                  overflow: TextOverflow.ellipsis,
                  style: fwMono(t, size: 11, color: t.inkFaint)),
            ),
            Expanded(
              child: SelectableText(value,
                  style: TextStyle(fontSize: 12.5, color: t.inkSoft)),
            ),
          ]),
        ),
      Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: EdgeInsets.zero,
          title:
              Text('Raw JSON', style: fwMono(t, size: 11.5, color: t.inkMuted)),
          children: [
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 320),
              child: SingleChildScrollView(
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: SelectableText(
                      const JsonEncoder.withIndent('  ').convert(result),
                      style: fwMono(t, size: 11, color: t.inkSoft)),
                ),
              ),
            ),
          ],
        ),
      ),
    ]);
  }
}
