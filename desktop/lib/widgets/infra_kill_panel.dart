// infra_kill_panel.dart -- the kill switch, and the two people who turn it.
//
// One operator typing the same name twice is a one-person rule wearing a
// two-person label, so the engine refuses identical authorities and this
// panel refuses to send them. The receipt is sealed whether the switch fires
// or not: a refused request is still the record that someone asked.
//
// Nothing here fires for real unless FLYWHEEL_KILL_SWITCH_LIVE is set in the
// engine's environment. Every action then reports executed false and says
// why, and this panel shows that rather than a green light it did not earn.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'operation_grant_sheet.dart';

/// The kill switch's own vocabulary. A name this list does not carry is
/// refused during canonicalization, so the list is not decoration.
const _actions = <String, String>{
  'network-isolation': 'block outbound network traffic',
  'credential-revocation': 'revoke every credential the agent can reach',
  'process-termination': 'terminate the agent process and its children',
  'compute-cutoff': 'stop the compute instance running the agent',
};

class KillSwitchPanel extends StatefulWidget {
  final GatewayClient client;
  const KillSwitchPanel({super.key, required this.client});

  @override
  State<KillSwitchPanel> createState() => _KillSwitchPanelState();
}

class _KillSwitchPanelState extends State<KillSwitchPanel> {
  final _reason = TextEditingController();
  final _first = TextEditingController();
  final _second = TextEditingController();
  final _selected = <String>{..._actions.keys};
  String _mode = 'evidence-preserving';
  Map<String, dynamic>? _receipt;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _reason.dispose();
    _first.dispose();
    _second.dispose();
    super.dispose();
  }

  /// The reason the switch cannot be thrown yet, or empty when it can.
  String get _blocked {
    if (_reason.text.trim().isEmpty) return 'A reason is required.';
    final a = _first.text.trim();
    final b = _second.text.trim();
    if (a.isEmpty || b.isEmpty) return 'Two authorities are required.';
    if (a == b) return 'The two authorities must be different people.';
    if (_selected.isEmpty) return 'Choose at least one action.';
    return '';
  }

  Future<void> _fire() async {
    if (_busy || _blocked.isNotEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final ordered =
          _actions.keys.where(_selected.contains).toList(growable: false);
      final r = await authorizeGatewayOperation<Map<String, dynamic>>(
        context,
        GatewayOperation.exact(
          action: 'infra.kill',
          clientRequestId: 'kill-${DateTime.now().microsecondsSinceEpoch}',
          operation: {
            'reason': _reason.text.trim(),
            'authority_1': _first.text.trim(),
            'authority_2': _second.text.trim(),
            'mode': _mode,
            'actions': ordered,
          },
        ),
        (body) => widget.client.postJson('/api/infra/kill', body,
            timeout: const Duration(minutes: 2)),
        currentOperation: () => null,
      );
      if (mounted) setState(() => _receipt = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final blocked = _blocked;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('kill switch · two authorities', hot: true),
          const SizedBox(height: FwLayout.s1),
          Text(
              'Evidence-preserving stops the agent and keeps what it wrote. '
              'Destructive does not. Both need two different people, and the '
              'request is sealed either way.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          TextField(
            controller: _reason,
            enabled: !_busy,
            onChanged: (_) => setState(() {}),
            style: fwMono(t, size: 11.5, color: t.ink),
            decoration:
                const InputDecoration(isDense: true, labelText: 'reason'),
          ),
          const SizedBox(height: FwLayout.s2),
          _authorityFields(t),
          const SizedBox(height: FwLayout.s3),
          const Kicker('mode'),
          const SizedBox(height: FwLayout.s2),
          _modeChoice(),
          const SizedBox(height: FwLayout.s3),
          const Kicker('actions'),
          for (final entry in _actions.entries)
            CheckboxListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              controlAffinity: ListTileControlAffinity.leading,
              value: _selected.contains(entry.key),
              onChanged: _busy
                  ? null
                  : (on) => setState(() => on == true
                      ? _selected.add(entry.key)
                      : _selected.remove(entry.key)),
              title: Text(entry.key,
                  style: fwMono(t, size: 11.5, color: t.ink)),
              subtitle: Text(entry.value,
                  style: fwMono(t, size: 10.5, color: t.inkFaint)),
            ),
          const SizedBox(height: FwLayout.s3),
          FilledButton(
            onPressed: _busy || blocked.isNotEmpty ? null : _fire,
            child: Text(_busy ? 'Asking…' : 'Throw the switch'),
          ),
          if (blocked.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            Text(blocked, style: fwMono(t, size: 11, color: t.inkFaint)),
          ],
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('The switch was not reached: $_error'),
          ],
          if (_receipt != null) ...[
            const SizedBox(height: FwLayout.s3),
            _result(t, _receipt!),
          ],
        ],
      ),
    );
  }

  Widget _authorityFields(FwTokens t) {
    final first = TextField(
      controller: _first,
      enabled: !_busy,
      onChanged: (_) => setState(() {}),
      style: fwMono(t, size: 11.5, color: t.ink),
      decoration:
          const InputDecoration(isDense: true, labelText: 'authority one'),
    );
    final second = TextField(
      controller: _second,
      enabled: !_busy,
      onChanged: (_) => setState(() {}),
      style: fwMono(t, size: 11.5, color: t.ink),
      decoration:
          const InputDecoration(isDense: true, labelText: 'authority two'),
    );
    return LayoutBuilder(builder: (context, box) {
      if (box.maxWidth < 420) {
        return Column(children: [
          first,
          const SizedBox(height: FwLayout.s2),
          second,
        ]);
      }
      return Row(children: [
        Expanded(child: first),
        const SizedBox(width: FwLayout.s3),
        Expanded(child: second),
      ]);
    });
  }

  Widget _modeChoice() {
    return SegmentedButton<String>(
      segments: const [
        ButtonSegment(
            value: 'evidence-preserving', label: Text('evidence-preserving')),
        ButtonSegment(value: 'destructive', label: Text('destructive')),
      ],
      selected: {_mode},
      showSelectedIcon: false,
      onSelectionChanged:
          _busy ? null : (s) => setState(() => _mode = s.first),
    );
  }

  Widget _result(FwTokens t, Map<String, dynamic> receipt) {
    final body =
        (receipt['seal_body'] as Map?)?.cast<String, dynamic>() ?? {};
    // The receipt's own `executed` records that two authorities confirmed the
    // request. Whether anything actually ran is a separate fact, and both are
    // shown, because collapsing them would report a shutdown that never was.
    final authorized = body['executed'] == true;
    final ran = receipt['any_executed'] == true;
    final results = receipt['action_results'];
    final rows = results is List
        ? results.whereType<Map>().map((m) => m.cast<String, dynamic>())
        : const <Map<String, dynamic>>[];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          VerdictPill(authorized ? 'AUTHORIZED' : 'REFUSED',
              status: authorized ? 'verified' : 'drift'),
          const SizedBox(width: FwLayout.s3),
          VerdictPill(ran ? 'ACTIONS RAN' : 'NOTHING RAN',
              status: ran ? 'drift' : 'unverifiable'),
        ]),
        if (!authorized) ...[
          const SizedBox(height: FwLayout.s2),
          HonestNull('${body['refusal_reason'] ?? 'The switch refused the '
              'request. Two different authorities are required.'}'),
        ],
        const SizedBox(height: FwLayout.s2),
        for (final r in rows)
          Text(
              '${r['action'] ?? '?'} · executed ${r['executed'] == true} · '
              '${r['reason'] ?? r['detail'] ?? 'no reason recorded'}',
              style: fwMono(t, size: 11, color: t.inkSoft)),
        const SizedBox(height: FwLayout.s2),
        HashText('seal', '${receipt['seal_hash'] ?? ''}', keep: 24),
      ],
    );
  }
}
