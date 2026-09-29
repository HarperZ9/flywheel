// lane_console.dart - run one lane's tools from its card.
//
// Listing the tools starts the lane, so it asks for the same approval as a
// plugin probe (POST /api/lanes/<lane>/tools under a plugin.probe grant).
// Running a tool is one lane.call the owner approves: the grant names the
// lane, the tool, the arguments, the policy timeout and, above T1, the tier.
// The desktop waits the policy timeout plus 10 s. The answer renders as rows
// with the raw JSON folded; a failure renders its fixed code, one sentence and
// one action.

import 'dart:async';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../controllers/gateway_operation_controller.dart';
import '../models/lane_models.dart';
import '../models/lane_tool_spec.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'lane_error_view.dart';
import 'lane_result_view.dart';
import 'lane_setup_list.dart';
import 'lane_tool_picker.dart';
import 'operation_grant_sheet.dart';

/// How long the desktop waits for a tool listing: the engine's 20 s plus 10.
const laneListingWait = Duration(seconds: 30);

class LaneConsole extends StatefulWidget {
  final GatewayClient client;
  final Lane lane;

  /// Probe this lane now; the action under a launch failure.
  final void Function(String name)? onCheck;
  final LaneSetupPickers pickers;
  const LaneConsole({
    super.key,
    required this.client,
    required this.lane,
    this.onCheck,
    this.pickers = const LaneSetupPickers(),
  });

  @override
  State<LaneConsole> createState() => _LaneConsoleState();
}

class _LaneConsoleState extends State<LaneConsole> {
  LaneToolListing? _listing;
  LaneToolSpec? _tool;
  Map<String, dynamic> _args = const {};
  List<String> _missing = const [];
  bool _busy = false;
  Object? _result;
  bool _answered = false;
  LaneError? _error;
  String? _note;
  final _setupKey = GlobalKey();
  var _request = 0;

  String get _lane => widget.lane.name;
  String _requestId(String kind) =>
      'lane-$kind-${DateTime.now().microsecondsSinceEpoch}-${++_request}';

  void _begin() => setState(() {
        _busy = true;
        _error = null;
        _note = null;
      });

  Future<void> _listTools() async {
    if (_busy) return;
    _begin();
    try {
      final operation = GatewayOperation.pluginProbe(
          name: _lane, clientRequestId: _requestId('tools'));
      final answer = await _authorized(operation,
          '/api/lanes/${Uri.encodeComponent(_lane)}/tools', laneListingWait);
      if (answer == null || !mounted) return;
      final error = LaneError.of(answer);
      final listing = LaneToolListing.tryParse(answer.body, _lane);
      setState(() {
        _error = error ?? (listing == null ? const LaneError('NO_BODY') : null);
        if (listing != null) _listing = listing;
        if (_tool != null && listing != null) {
          _tool =
              listing.runnable.where((t) => t.name == _tool!.name).firstOrNull;
        }
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _run() async {
    final tool = _tool;
    if (tool == null || _busy) return;
    if (_missing.isNotEmpty) {
      setState(
          () => _note = 'Fill the required fields: ${_missing.join(', ')}.');
      return;
    }
    _begin();
    try {
      final request = _requestId('call');
      final operation = laneCallOperation(_lane, tool, _args, request);
      final path = '/api/lane/${Uri.encodeComponent(_lane)}/'
          '${Uri.encodeComponent(tool.name)}';
      final answer = await _authorized(operation, path, tool.clientWait,
          current: () => _currentCall(tool, request));
      if (answer == null || !mounted) return;
      final error = LaneError.of(answer);
      setState(() {
        _error = error;
        _answered = error == null;
        _result = error == null ? answer.body : null;
      });
    } on ArgumentError {
      if (mounted) {
        setState(() => _note = 'These arguments cannot go into an approval: '
            'a local path fits only a path argument of this tool.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  GatewayOperation? _currentCall(LaneToolSpec tool, String request) {
    try {
      return laneCallOperation(_lane, tool, _args, request);
    } on ArgumentError {
      return null;
    }
  }

  /// Approve [operation], post it to [path], and wait [wait]. Null when the
  /// owner declined; a failed approval or a client timeout sets the error.
  Future<LaneAnswer?> _authorized(
      GatewayOperation operation, String path, Duration wait,
      {GatewayOperationSupplier? current}) async {
    final outcome = await authorizeGatewayOperationDetailed<LaneAnswer>(
        context, operation, (body) => _post(path, body, wait),
        currentOperation: current ?? () => operation);
    final failure = outcome.failure;
    if (failure != null && mounted) {
      setState(() => _error = LaneError(failure.code));
    }
    if (outcome.denied && mounted) {
      setState(() => _note = 'The approval was declined; nothing ran.');
    }
    return outcome.value;
  }

  /// The answer, or a client timeout stated as an answer: the engine may
  /// still finish the call after the app stops waiting.
  Future<LaneAnswer> _post(
      String path, Map<String, dynamic> body, Duration wait) async {
    try {
      return await widget.client.postLaneAnswer(path, body, timeout: wait);
    } on TimeoutException {
      return (
        status: 0,
        body: {
          'code': 'CLIENT_TIMEOUT',
          'error': 'no answer',
          'timeout_s': wait.inSeconds
        }
      );
    }
  }

  void _act(LaneErrorAction action) => switch (action) {
        LaneErrorAction.listTools => unawaited(_listTools()),
        LaneErrorAction.runAgain => unawaited(_run()),
        LaneErrorAction.checkLane => widget.onCheck?.call(_lane),
        LaneErrorAction.showSetup => _showSetup(),
        LaneErrorAction.none => null,
      };

  void _showSetup() {
    final target = _setupKey.currentContext;
    if (target != null) Scrollable.ensureVisible(target);
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final listing = _listing;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('run a tool'),
      Text(
          'Listing the tools starts the lane, so it asks for the same '
          'approval as a plugin probe. Each run asks for its own.',
          style: TextStyle(fontSize: 12, color: t.inkMuted, height: 1.4)),
      LaneSetupList(
          key: _setupKey,
          client: widget.client,
          lane: widget.lane,
          pickers: widget.pickers,
          onChanged: () => widget.onCheck?.call(_lane)),
      const SizedBox(height: FwLayout.s2),
      OutlinedButton(
          onPressed: _busy ? null : _listTools,
          child: Text(listing == null ? 'List tools' : 'List again')),
      if (listing != null) ...[
        const SizedBox(height: FwLayout.s2),
        LaneToolList(
            listing: listing, selected: _tool?.name, onSelect: _select),
      ],
      if (_tool != null) ...[
        const SizedBox(height: FwLayout.s3),
        LaneToolPanel(
            tool: _tool!,
            busy: _busy,
            onChanged: (args, missing) {
              _args = args;
              _missing = missing;
            },
            onRun: _run),
      ],
      ..._outcome(),
    ]);
  }

  void _select(LaneToolSpec tool) => setState(() {
        _tool = tool;
        _answered = false;
        _error = null;
      });

  /// The note, the error or the answer under the form.
  List<Widget> _outcome() => [
        if (_note != null) HonestNull(_note!),
        if (_error != null)
          LaneErrorView(
              error: _error!,
              lane: widget.lane,
              tool: _tool?.name ?? 'the tool list',
              onAction: _act),
        if (_answered && _tool != null)
          LaneResultView(tool: _tool!.name, result: _result),
      ];
}
