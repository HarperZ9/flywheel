// family_view.dart — the ecosystem status board as a living surface: the
// readiness receipt per tool, the comprehension ledger (ownership from
// checked evidence), retention due with outcome recording, and the store
// chain's live verdict. Every number is a fetch of a route a stranger
// could call; nothing here is asserted.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class FamilyView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const FamilyView({super.key, required this.client, required this.alive});

  @override
  State<FamilyView> createState() => _FamilyViewState();
}

class _FamilyViewState extends State<FamilyView> {
  Map<String, dynamic>? _readiness;
  Map<String, dynamic>? _comprehension;
  Map<String, dynamic>? _retention;
  Map<String, dynamic>? _chain;
  final Map<String, String> _recorded = {};
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(FamilyView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  Future<void> _load() async {
    if (!widget.alive) return;
    try {
      final results = await Future.wait([
        widget.client.getJson('/api/readiness'),
        widget.client.getJson('/api/comprehension'),
        widget.client.getJson('/api/retention?days=3'),
        widget.client.getJson('/api/store/verify'),
      ]);
      if (mounted) {
        setState(() {
          _readiness = results[0];
          _comprehension = results[1];
          _retention = results[2];
          _chain = results[3];
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _record(String eid, bool passed) async {
    setState(() => _recorded[eid] = 'recording…');
    try {
      final r = await widget.client.retentionRecord(eid, passed);
      setState(() => _recorded[eid] = r['error'] != null
          ? 'failed: ${r['error']}'
          : 'banked ${passed ? 'pass' : 'fail'} · ${r['stored']}');
    } catch (e) {
      setState(() => _recorded[eid] = 'failed: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. The family board appears when it runs.',
          command: 'flywheel up');
    }
    final t = context.fw;
    final r = _readiness;
    return ViewScroll(
      children: [
        SectionHeader('Family',
            kicker: 'the ecosystem, measured not felt',
            trailing: OutlinedButton(
                onPressed: _load, child: const Text('Refresh'))),
        const SizedBox(height: FwLayout.s3),
        if (_error != null) HonestNull('Failed: $_error'),
        if (r != null) ...[
          AdaptiveTiles(children: [
            StatTile(
                label: 'tools ready',
                value: '${r['ready_count']}/${r['total']}',
                status: r['all_ready'] == true ? 'verified' : 'drift'),
            StatTile(
                label: 'audit chain',
                value: _chain?['ok'] == true
                    ? 'ok · ${_chain?['checked']}'
                    : 'broken',
                status: _chain?['ok'] == true ? 'verified' : 'drift'),
            StatTile(
                label: 'held files',
                value:
                    '${((_comprehension?['files'] ?? {}) as Map).length}'),
          ]),
          const SizedBox(height: FwLayout.s4),
          const Kicker('release readiness · per tool', hot: true),
          const SizedBox(height: FwLayout.s2),
          HairlineCard(
            child: Column(children: [
              for (final tool in ((r['tools'] ?? []) as List)
                  .whereType<Map<String, dynamic>>())
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(children: [
                    SizedBox(
                        width: 170,
                        child: Text('${tool['name']}',
                            style: fwMono(t, size: 11.5))),
                    VerdictPill(
                        tool['ready'] == true
                            ? 'ready'
                            : (tool['gaps'] as List?)?.join(', ') ?? 'gaps',
                        status:
                            tool['ready'] == true ? 'verified' : 'drift'),
                  ]),
                ),
            ]),
          ),
        ],
        if (_comprehension != null &&
            (_comprehension!['files'] as Map).isNotEmpty) ...[
          const SizedBox(height: FwLayout.s4),
          const Kicker('comprehension ledger · checked evidence'),
          const SizedBox(height: FwLayout.s2),
          HairlineCard(
            child: Column(children: [
              for (final e in (_comprehension!['files']
                      as Map<String, dynamic>)
                  .entries
                  .take(12))
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(children: [
                    Expanded(
                        child: Text(e.key, style: fwMono(t, size: 11.5))),
                    Text(
                        '${(e.value as Map)['holder']} · '
                        '${(e.value as Map)['kind']}',
                        style:
                            fwMono(t, size: 11, color: t.inkMuted)),
                  ]),
                ),
            ]),
          ),
        ],
        if (_retention != null) ...[
          const SizedBox(height: FwLayout.s4),
          const Kicker('retention · due for an unaided retest'),
          const SizedBox(height: FwLayout.s2),
          if ((_retention!['due'] as List).isEmpty)
            Text('Nothing due. What was demonstrated recently still counts '
                'as recent.',
                style: TextStyle(fontSize: 12.5, color: t.inkMuted))
          else
            HairlineCard(
              child: Column(children: [
                for (final d in (_retention!['due'] as List)
                    .whereType<Map<String, dynamic>>())
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Row(children: [
                      Expanded(
                          child: Text(
                              '${d['eid']} · ${d['kind']} · '
                              '${d['age_days']}d old',
                              style: fwMono(t, size: 11.5))),
                      if (_recorded['${d['eid']}'] != null)
                        Text(_recorded['${d['eid']}']!,
                            style: fwMono(t, size: 11, color: t.inkMuted))
                      else ...[
                        OutlinedButton(
                            onPressed: () => _record('${d['eid']}', true),
                            child: const Text('held')),
                        const SizedBox(width: FwLayout.s2),
                        OutlinedButton(
                            onPressed: () => _record('${d['eid']}', false),
                            child: const Text('lost')),
                      ],
                    ]),
                  ),
              ]),
            ),
        ],
      ],
    );
  }
}
