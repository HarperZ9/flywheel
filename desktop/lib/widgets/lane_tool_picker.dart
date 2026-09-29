// lane_tool_picker.dart - the lane console's tool list and the chosen tool's
// form.
//
// The runnable tools come first, main tools marked. A tool this build leaves
// out, or does not admit, is still listed, disabled, with the engine's reason,
// so a person sees what exists and why it does not run here. The chosen tool
// renders its argument form from its input schema (ToolForm) and states its
// tier and how long the call may take.

import 'package:flutter/material.dart';

import '../models/lane_tool_spec.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'tool_form.dart';

class LaneToolList extends StatelessWidget {
  final LaneToolListing listing;
  final String? selected;
  final void Function(LaneToolSpec tool) onSelect;
  const LaneToolList({
    super.key,
    required this.listing,
    required this.selected,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final blocked = listing.blocked;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
        for (final tool in listing.runnable)
          ChoiceChip(
            label: Text(tool.main ? '${tool.name} (main)' : tool.name,
                style: fwMono(t, size: 11.5)),
            selected: tool.name == selected,
            onSelected: (_) => onSelect(tool),
          ),
      ]),
      if (listing.runnable.isEmpty)
        const HonestNull('No tool on this lane runs in this build.'),
      if (blocked.isNotEmpty) ...[
        const SizedBox(height: FwLayout.s2),
        for (final tool in blocked)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Row(children: [
              ChoiceChip(
                label: Text(tool.name, style: fwMono(t, size: 11.5)),
                selected: false,
                onSelected: null,
              ),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: Text(tool.blockedReason,
                    style: TextStyle(fontSize: 12, color: t.inkMuted)),
              ),
            ]),
          ),
      ],
    ]);
  }
}

class LaneToolPanel extends StatelessWidget {
  final LaneToolSpec tool;
  final bool busy;
  final void Function(Map<String, dynamic> args, List<String> missing)
      onChanged;
  final VoidCallback onRun;
  const LaneToolPanel({
    super.key,
    required this.tool,
    required this.busy,
    required this.onChanged,
    required this.onRun,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final soft = TextStyle(fontSize: 12, color: t.inkMuted, height: 1.4);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (tool.description.isNotEmpty) Text(tool.description, style: soft),
      Text(_tierLine(tool), style: soft),
      const SizedBox(height: FwLayout.s3),
      ToolForm(key: ValueKey(tool.name), spec: tool.spec, onChanged: onChanged),
      Align(
        alignment: Alignment.centerLeft,
        child: FilledButton(
          onPressed: busy ? null : onRun,
          child: Text(busy ? 'Running...' : 'Run'),
        ),
      ),
    ]);
  }
}

String _tierLine(LaneToolSpec tool) {
  final wait = 'The engine waits up to ${tool.timeoutS} s.';
  return tool.needsTier
      ? '${tool.tier}: the approval names this tier. $wait'
      : 'T1. $wait';
}
