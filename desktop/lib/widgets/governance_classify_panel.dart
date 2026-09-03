// governance_classify_panel.dart -- classify a system against TADR Stage A.
//
// The tier table said what the tiers ARE. Nothing in the app could ask what
// tier a given system lands in, so the route existed and the operator could
// not reach it. The consequence vocabulary comes from the engine's own tier
// document, never from a copy kept here: a local list would offer a word the
// engine refuses the day the manual gains one.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class GovernanceClassifyPanel extends StatefulWidget {
  final GatewayClient client;

  /// The engine's own Stage A vocabulary, in tier order.
  final List<String> t2Overrides, t3Overrides;

  const GovernanceClassifyPanel(
      {super.key,
      required this.client,
      required this.t2Overrides,
      required this.t3Overrides});

  @override
  State<GovernanceClassifyPanel> createState() =>
      _GovernanceClassifyPanelState();
}

class _GovernanceClassifyPanelState extends State<GovernanceClassifyPanel> {
  final _selected = <String>{};
  Map<String, dynamic>? _result;
  String? _error;
  bool _busy = false;

  Future<void> _classify() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final query = _selected
        .map((o) => 'override=${Uri.encodeQueryComponent(o)}')
        .join('&');
    try {
      final r = await widget.client
          .getJson('/api/governance/classify${query.isEmpty ? '' : '?$query'}');
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
    final known = [...widget.t3Overrides, ...widget.t2Overrides];
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('classify'),
          const SizedBox(height: FwLayout.s1),
          Text(
              'Stage A asks what the worst credible consequence is, not what '
              'is most likely. Selecting a T3 consequence fixes the tier at '
              'T3; the classification never de-escalates below the floor an '
              'override sets.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          if (known.isEmpty)
            const HonestNull(
                'The engine did not report a consequence vocabulary, so no '
                'override can be offered.')
          else
            Wrap(
              spacing: FwLayout.s2,
              runSpacing: 4,
              children: [
                for (final override in known)
                  FilterChip(
                    label: Text(override, style: fwMono(t, size: 10.5)),
                    selected: _selected.contains(override),
                    onSelected: (on) => setState(() =>
                        on ? _selected.add(override) : _selected.remove(override)),
                  ),
              ],
            ),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            FilledButton(
              onPressed: _busy || known.isEmpty ? null : _classify,
              child: Text(_busy ? 'Classifying…' : 'Classify'),
            ),
            const SizedBox(width: FwLayout.s3),
            if (_selected.isNotEmpty)
              TextButton(
                onPressed: _busy ? null : () => setState(_selected.clear),
                child: const Text('Clear'),
              ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull('The classification failed: $_error'),
          ],
          if (_result != null) ...[
            const SizedBox(height: FwLayout.s3),
            _verdict(t, _result!),
          ],
        ],
      ),
    );
  }

  Widget _verdict(FwTokens t, Map<String, dynamic> r) {
    final tier = '${r['tier'] ?? 'unknown'}';
    final modifiers = r['modifiers'] is List ? (r['modifiers'] as List) : const [];
    final triggered = r['triggered_overrides'] is List
        ? (r['triggered_overrides'] as List)
        : const [];
    final rationale = '${r['rationale'] ?? ''}';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          // Tier is a governance demand, not a pass or a fail, so it carries
          // the neutral mark rather than a verdict color.
          VerdictPill(
              modifiers.isEmpty
                  ? tier
                  : '$tier-${modifiers.map((m) => '$m').join('/')}',
              status: 'unverifiable'),
          const SizedBox(width: FwLayout.s3),
          Text('uncertainty ${r['uncertainty'] ?? 'unstated'}',
              style: fwMono(t, size: 11).copyWith(color: t.inkMuted)),
        ]),
        if (triggered.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Text('triggered: ${triggered.join(', ')}',
              style: fwMono(t, size: 11).copyWith(color: t.inkSoft)),
        ],
        if (rationale.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Text(rationale,
              style: TextStyle(fontSize: 12.5, height: 1.5, color: t.inkMuted)),
        ],
      ],
    );
  }
}
