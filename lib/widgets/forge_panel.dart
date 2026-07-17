// forge_panel.dart — the prompt forge, in the app where it can do more:
// a plain goal becomes a structured prompt whose success gates a machine
// can check, both arms sealed by hash, and drift re-checkable in place.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ForgePanel extends StatefulWidget {
  final GatewayClient client;
  const ForgePanel({super.key, required this.client});

  @override
  State<ForgePanel> createState() => _ForgePanelState();
}

class _ForgePanelState extends State<ForgePanel> {
  final _goal = TextEditingController();
  Map<String, dynamic>? _doc;
  Map<String, dynamic>? _recheck;
  bool _busy = false, _rechecking = false;
  String? _error;

  @override
  void dispose() {
    _goal.dispose();
    super.dispose();
  }

  Future<void> _forge() async {
    final goal = _goal.text.trim();
    if (goal.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _recheck = null;
    });
    try {
      final r = await widget.client.forge(goal);
      if (mounted) setState(() => _doc = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _driftCheck() async {
    final prp = '${_doc?['prp_id'] ?? ''}';
    if (prp.isEmpty || _rechecking) return;
    setState(() => _rechecking = true);
    try {
      final r = await widget.client.forgeRecheck(prp);
      if (mounted) setState(() => _recheck = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _rechecking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final d = _doc;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
              'A goal with a machine-checkable outcome scores high; a vague '
              'one scores low and says so. Both arms seal at forge time, so '
              'drift has nowhere to hide.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _goal,
                style: const TextStyle(fontSize: 13),
                onSubmitted: (_) => _forge(),
                decoration: const InputDecoration(
                    hintText:
                        'a plain goal, e.g. parse a CSV file and pass the provided tests'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy ? null : _forge,
              child: Text(_busy ? 'Forging…' : 'Forge'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull('Forge failed: $_error'),
          ],
          if (d != null) ...[
            const SizedBox(height: FwLayout.s3),
            Row(children: [
              VerdictPill(
                  d['well_posed'] == true ? 'well-posed' : 'under-specified',
                  status: d['well_posed'] == true ? 'verified' : 'drift'),
              const SizedBox(width: FwLayout.s2),
              Text('${d['task_type'] ?? ''}', style: fwMono(t, size: 11.5)),
              const SizedBox(width: FwLayout.s3),
              Text(
                  'confidence ${d['confidence'] ?? '?'}   external gates '
                  '${(((d['external_gate_ratio'] ?? 0) as num) * 100).round()}%',
                  style: fwMono(t, size: 11.5).copyWith(color: t.inkMuted)),
            ]),
            if (d['validation_gates'] is List &&
                (d['validation_gates'] as List).isNotEmpty) ...[
              const SizedBox(height: FwLayout.s2),
              for (final gate in (d['validation_gates'] as List))
                Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Row(children: [
                    const VerdictDot('verified'),
                    const SizedBox(width: FwLayout.s2),
                    Expanded(
                        child: Text('$gate',
                            style: fwMono(t, size: 11.5)
                                .copyWith(color: t.inkSoft))),
                  ]),
                ),
            ],
            const SizedBox(height: FwLayout.s2),
            Container(
              width: double.infinity,
              constraints: const BoxConstraints(maxHeight: 220),
              padding: const EdgeInsets.all(FwLayout.s3),
              decoration: BoxDecoration(
                  border: Border.all(color: t.hairline),
                  borderRadius: BorderRadius.circular(4)),
              child: Stack(children: [
                SingleChildScrollView(
                  child: SelectableText('${d['prompt'] ?? ''}',
                      style: fwMono(t, size: 11.5).copyWith(color: t.inkSoft)),
                ),
                Positioned(
                  top: 0,
                  right: 0,
                  child: IconButton(
                    tooltip: 'Copy the forged prompt',
                    icon: const Icon(Icons.copy, size: 14),
                    onPressed: () => Clipboard.setData(
                        ClipboardData(text: '${d['prompt'] ?? ''}')),
                  ),
                ),
              ]),
            ),
            const SizedBox(height: FwLayout.s2),
            HashText('intent', '${d['intent_sha256'] ?? ''}', keep: 16),
            HashText('architecture', '${d['architecture_sha256'] ?? ''}',
                keep: 16),
            const SizedBox(height: FwLayout.s3),
            Row(children: [
              OutlinedButton(
                onPressed: _rechecking ? null : _driftCheck,
                child: Text(_rechecking ? 'Rechecking…' : 'Recheck drift'),
              ),
              const SizedBox(width: FwLayout.s3),
              if (_recheck != null)
                Expanded(child: _recheckRow(t, _recheck!)),
            ]),
          ],
        ],
      ),
    );
  }

  Widget _recheckRow(FwTokens t, Map<String, dynamic> r) {
    final pills = <Widget>[];
    r.forEach((k, v) {
      final s = '$v'.toUpperCase();
      if (s == 'MATCH' || s == 'DRIFT') {
        pills.add(Padding(
          padding: const EdgeInsets.only(right: FwLayout.s2),
          child: VerdictPill('$k $s',
              status: s == 'MATCH' ? 'verified' : 'drift'),
        ));
      }
    });
    if (pills.isEmpty) {
      return Text('${r['note'] ?? r['error'] ?? r}',
          style: fwMono(t, size: 11).copyWith(color: t.inkMuted),
          overflow: TextOverflow.ellipsis);
    }
    return Wrap(runSpacing: 4, children: pills);
  }
}
