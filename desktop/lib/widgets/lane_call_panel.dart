// lane_call_panel.dart -- call one lane tool, with the grant naming the target.
//
// The path names the lane and the tool; so does the grant. The engine refuses
// with a 409 when they disagree, because a grant attesting to one target while
// the route runs another is not a grant. Calling spawns the lane's MCP server,
// so this is execution and never a plain button.

import 'dart:convert';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/callable_lane.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'operation_grant_sheet.dart';

class LaneCallPanel extends StatefulWidget {
  final GatewayClient client;
  const LaneCallPanel({super.key, required this.client});

  @override
  State<LaneCallPanel> createState() => _LaneCallPanelState();
}

class _LaneCallPanelState extends State<LaneCallPanel> {
  final _tool = TextEditingController();
  final _args = TextEditingController(text: '{}');
  List<CallableLane> _lanes = const [];
  String? _lane;
  Map<String, dynamic>? _result;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _loadLanes();
  }

  @override
  void dispose() {
    _tool.dispose();
    _args.dispose();
    super.dispose();
  }

  Future<void> _loadLanes() async {
    try {
      final json = await widget.client.callableLanes();
      if (mounted) setState(() => _lanes = CallableLane.listFrom(json));
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _call() async {
    final lane = _lane;
    final tool = _tool.text.trim();
    if (lane == null || lane.isEmpty || tool.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final decoded =
          jsonDecode(_args.text.trim().isEmpty ? '{}' : _args.text.trim());
      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('args must be a JSON object');
      }
      final requestId = 'lane-${DateTime.now().microsecondsSinceEpoch}';
      final r = await authorizeGatewayOperation<Map<String, dynamic>>(
        context,
        GatewayOperation.exact(
          action: 'lane.call',
          clientRequestId: requestId,
          operation: {'name': lane, 'tool': tool, 'args': decoded},
        ),
        (body) => widget.client.postJsonLenient('/api/lane/$lane/$tool', body,
            timeout: const Duration(minutes: 2)),
        currentOperation: () => null,
      );
      if (mounted) setState(() => _result = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('call a lane tool'),
          const SizedBox(height: FwLayout.s1),
          Text(
              'The grant names the lane and the tool. If they disagree with '
              'the route, the engine refuses rather than running the one it '
              'was not asked to run.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            SizedBox(
              width: 200,
              child: DropdownButtonFormField<String>(
                initialValue: _lane,
                isExpanded: true,
                decoration: const InputDecoration(
                    isDense: true, labelText: 'lane'),
                style: fwMono(t, size: 11.5, color: t.ink),
                items: [
                  for (final lane in _lanes)
                    DropdownMenuItem(
                        value: lane.name, child: Text(lane.name)),
                ],
                onChanged: _busy ? null : (v) => setState(() => _lane = v),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            Expanded(
              child: TextField(
                controller: _tool,
                enabled: !_busy,
                style: fwMono(t, size: 11.5, color: t.ink),
                decoration:
                    const InputDecoration(isDense: true, labelText: 'tool'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy || _lane == null ? null : _call,
              child: Text(_busy ? 'Calling…' : 'Call'),
            ),
          ]),
          const SizedBox(height: FwLayout.s2),
          TextField(
            controller: _args,
            enabled: !_busy,
            maxLines: 3,
            style: fwMono(t, size: 11.5, color: t.ink),
            decoration: const InputDecoration(
                isDense: true, labelText: 'args (JSON object)'),
          ),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The call did not run: $_error'),
          ],
          if (_result != null) ...[
            const SizedBox(height: FwLayout.s3),
            _resultBlock(t, _result!),
          ],
        ],
      ),
    );
  }

  Widget _resultBlock(FwTokens t, Map<String, dynamic> r) {
    // Governance refusal is an ANSWER from the lane layer, not a transport
    // fault, so it is rendered as the verdict it is.
    if (r['governance_denied'] != null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const VerdictPill('GOVERNANCE DENIED', status: 'drift'),
          const SizedBox(height: FwLayout.s2),
          SelectableText('${r['governance_denied']}',
              style: fwMono(t, size: 11, color: t.inkSoft)),
        ],
      );
    }
    if (r['error'] != null) {
      return HonestNull('The lane refused: ${r['error']}');
    }
    return SelectableText(
        const JsonEncoder.withIndent('  ').convert(r),
        style: fwMono(t, size: 11, color: t.inkSoft));
  }
}
