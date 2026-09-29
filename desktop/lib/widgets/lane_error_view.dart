// lane_error_view.dart - one failed lane call, stated from its fixed code.
//
// The engine answers a failed lane call with one code from a closed set and a
// reason slug, never tool or stderr text (PLAN section 2, O-7 default). Each
// code gets one sentence and one action here. A code outside the set (a
// refused grant, a journey the approval needs) is stated as the engine named
// it, with no action.

import 'package:flutter/material.dart';

import '../models/lane_models.dart';
import '../models/lane_tool_spec.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

/// What the one button under a lane error does.
enum LaneErrorAction { listTools, showSetup, checkLane, runAgain, none }

/// The one action under each code; a code outside the set gets none.
const _actions = {
  'CAPABILITY_NOT_ADMITTED': (LaneErrorAction.listTools, 'List tools again'),
  'NOT_IN_BUILD': (LaneErrorAction.listTools, 'List tools again'),
  'LANE_SETUP_REQUIRED': (LaneErrorAction.showSetup, 'Show setup'),
  'LANE_CANNOT_LAUNCH': (LaneErrorAction.checkLane, 'Check the lane'),
  'LANE_TIMEOUT': (LaneErrorAction.runAgain, 'Run again'),
  'LANE_TOOL_ERROR': (LaneErrorAction.runAgain, 'Run again'),
  'CLIENT_TIMEOUT': (LaneErrorAction.runAgain, 'Run again'),
};

/// The sentence and the action for [error] on [tool] of [lane].
({String text, LaneErrorAction action, String label}) laneErrorCopy(
    LaneError error, Lane lane, String tool) {
  final (action, label) = _actions[error.code] ?? (LaneErrorAction.none, '');
  return (text: laneErrorText(error, lane, tool), action: action, label: label);
}

/// One sentence per code, from the closed fields only.
String laneErrorText(LaneError error, Lane lane, String tool) {
  final why = error.reason.isEmpty ? '' : ' (${error.reason})';
  return switch (error.code) {
    'CAPABILITY_NOT_ADMITTED' => error.admitted.isEmpty
        ? 'This build does not admit $tool.'
        : 'This build does not admit $tool. Admitted: '
            '${error.admitted.join(', ')}.',
    'NOT_IN_BUILD' => 'Not in this build: $tool$why.',
    'LANE_SETUP_REQUIRED' => '${lane.name} needs a setup step first: '
        '${_setupNames(error.setup, lane)}.',
    'LANE_CANNOT_LAUNCH' =>
      'Could not start: ${error.reason.isEmpty ? 'unknown' : error.reason}.',
    'LANE_TIMEOUT' => error.timeoutS == null
        ? '$tool did not answer in time.'
        : '$tool did not answer within ${error.timeoutS} s.',
    'LANE_TOOL_ERROR' =>
      '$tool reported an error$why. The tool text is not shown.',
    'CLIENT_TIMEOUT' =>
      'No answer reached the app within ${error.timeoutS ?? 0} s. '
          'The engine may still finish the call.',
    'GOVERNANCE_DENIED' => 'The engine refused $tool at this tier.',
    _ => 'The engine refused the call: ${error.code}$why.',
  };
}

String _setupNames(List<String> ids, Lane lane) {
  if (ids.isEmpty) return 'see the setup list';
  final titles = {for (final item in lane.setup) item.id: item.title};
  return ids
      .map((id) => (titles[id] ?? '').isEmpty ? id : titles[id]!)
      .join(', ');
}

class LaneErrorView extends StatelessWidget {
  final LaneError error;
  final Lane lane;
  final String tool;
  final void Function(LaneErrorAction action) onAction;
  const LaneErrorView({
    super.key,
    required this.error,
    required this.lane,
    required this.tool,
    required this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final copy = laneErrorCopy(error, lane, tool);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        VerdictPill(error.code, status: 'drift'),
        const SizedBox(width: FwLayout.s2),
        Expanded(
          child: Text(copy.text,
              style: TextStyle(fontSize: 12.5, color: t.inkSoft, height: 1.4)),
        ),
      ]),
      if (copy.action != LaneErrorAction.none) ...[
        const SizedBox(height: FwLayout.s2),
        OutlinedButton(
            onPressed: () => onAction(copy.action), child: Text(copy.label)),
      ],
    ]);
  }
}
