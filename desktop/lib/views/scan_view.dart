// scan_view.dart -- the Scan destination: what the code scan found, and
// what makes the empty result mean something.
//
// A scan that found nothing and a scan that looked at nothing print the
// same number. Three things separate them, and all three are on this
// page beside the counts: the corpus (how many files were read, and
// which ones were skipped), the ruleset (every rule proved itself on a
// snippet written to trip it), and the suppressions (findings somebody
// accepted, counted where a reader sees them).
//
// `clean` is stricter than an empty finding list, so the word is printed
// only when the engine earns it.
import 'package:flutter/material.dart';

import '../client/gateway_error.dart';
import '../client/gateway_scan.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

/// The findings drawn on the page. The counts are the engine's and cover
/// every finding, so this shortens a list and never a number.
const _findingsShown = 25;

class ScanView extends StatefulWidget {
  final ScanApi api;
  final bool alive;
  const ScanView({super.key, required this.api, required this.alive});

  @override
  State<ScanView> createState() => _ScanViewState();
}

class _ScanViewState extends State<ScanView> {
  Map<String, dynamic>? _roster;
  Map<String, dynamic>? _scan;
  Map<String, dynamic>? _verify;
  String? _refused;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    if (widget.alive) _refresh();
  }

  Future<void> _refresh() async {
    setState(() => _busy = true);
    try {
      final body = await widget.api.latest();
      setState(() {
        _roster = body;
        _scan = _asMap(body['latest']);
        _verify = _asMap(body['verify']);
        _error = null;
      });
    } on GatewayException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'the scan history could not be read');
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _run() async {
    setState(() => _busy = true);
    try {
      final body = await widget.api.run();
      setState(() {
        _refused = body['scanned'] == false ? '${body['refused']}' : null;
        _error = null;
      });
    } on GatewayException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'the scan did not complete');
    } finally {
      setState(() => _busy = false);
    }
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty('The engine is offline. Start it to scan.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(storageKey: 'scan', children: [
      Row(children: [
        const Expanded(child: SectionHeader('Scan', kicker: 'code scan')),
        TextButton(
          key: const Key('scan-run'),
          onPressed: _busy ? null : _run,
          child: const Text('Run a scan'),
        ),
        IconButton(
          key: const Key('scan-refresh'),
          onPressed: _busy ? null : _refresh,
          tooltip: 'Re-read the last scan',
          icon: const Icon(Icons.refresh),
        ),
      ]),
      const SizedBox(height: FwLayout.s3),
      Text(
        'The scanned tree is the repository this engine serves; it is not '
        'a field a caller sets. Suppressions come from a file an operator '
        'edits, so no request can quiet a finding. Every rule runs against '
        'a snippet written to trip it on every scan.',
        style: TextStyle(fontSize: 13, height: 1.5, color: t.inkMuted),
      ),
      const SizedBox(height: FwLayout.s4),
      if (_error != null)
        Padding(
          padding: const EdgeInsets.only(bottom: FwLayout.s3),
          child: HonestNull(_error!),
        ),
      if (_refused != null)
        Padding(
          padding: const EdgeInsets.only(bottom: FwLayout.s3),
          child: HonestNull('Refused: $_refused'),
        ),
      if (_scan == null && !_busy)
        const HonestNull('No scan yet. Run one and it lands here.')
      else if (_scan != null) ...[
        _headline(),
        const SizedBox(height: FwLayout.s3),
        HairlineCard(child: _seals(context)),
        const SizedBox(height: FwLayout.s3),
        HairlineCard(child: _findings(context)),
      ],
    ]);
  }

  Widget _headline() {
    final counts = _asMap(_scan?['counts']) ?? const {};
    final clean = _scan?['clean'] == true;
    return Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s3, children: [
      StatTile(
          label: 'Verdict',
          value: clean ? 'clean' : 'open',
          status: clean ? 'verified' : 'drift'),
      StatTile(label: 'High', value: '${_int(counts['high'])}'),
      StatTile(label: 'Medium', value: '${_int(counts['medium'])}'),
      StatTile(label: 'Low', value: '${_int(counts['low'])}'),
      // Beside the verdict on purpose: a clean scan resting on accepted
      // findings would otherwise read as a scan that found nothing.
      StatTile(
          label: 'Suppressed', value: '${_int(_scan?['suppressed_count'])}'),
    ]);
  }

  Widget _seals(BuildContext context) {
    final t = context.fw;
    final skipped = (_scan?['skipped'] as List?) ?? const [];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('What the number rests on'),
      const SizedBox(height: FwLayout.s3),
      Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
        _flag('rules proved', _scan?['ruleset_proven'] == true),
        _flag('chain intact', _roster?['chain_intact'] == true),
        _flag('record sealed', _verify?['record_sealed'] == true),
        _flag('corpus matches', _verify?['corpus_matches'] == true),
        _flag('ruleset matches', _verify?['ruleset_matches'] == true),
      ]),
      const SizedBox(height: FwLayout.s3),
      Text(
        '${_int(_scan?['files_scanned'])} of '
        '${_int(_scan?['files_in_corpus'])} files read, across '
        '${_trees()}. Scanned at ${_scan?['scanned_at'] ?? ''}.',
        style: TextStyle(fontSize: 12.5, color: t.inkMuted),
      ),
      if (skipped.isNotEmpty) ...[
        const SizedBox(height: FwLayout.s2),
        HonestNull('${skipped.length} file(s) could not be read, so the '
            'corpus has a hole in it and the counts do not cover them.'),
      ],
    ]);
  }

  Widget _flag(String label, bool held) =>
      VerdictPill(label, status: held ? 'verified' : 'drift');

  String _trees() {
    final trees = ((_scan?['trees'] as List?) ?? const [])
        .map((t) => t.toString())
        .toList();
    return trees.isEmpty ? 'no named tree' : trees.join(', ');
  }

  Widget _findings(BuildContext context) {
    final t = context.fw;
    final all = ((_scan?['findings'] as List?) ?? const [])
        .whereType<Map>()
        .map((m) => m.map((k, v) => MapEntry(k.toString(), v)))
        .toList();
    final total = _int(_scan?['findings_total']);
    if (all.isEmpty) {
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Kicker('Findings'),
        const SizedBox(height: FwLayout.s2),
        Text('None open.', style: TextStyle(fontSize: 12.5, color: t.ink)),
      ]);
    }
    final shown = all.take(_findingsShown).toList();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('Findings'),
      const SizedBox(height: FwLayout.s2),
      for (final f in shown) ...[
        _finding(context, f, t),
        const SizedBox(height: FwLayout.s2),
      ],
      if (total > shown.length)
        HonestNull('${total - shown.length} further finding(s) are counted '
            'above and not drawn here.'),
    ]);
  }

  Widget _finding(BuildContext context, Map<String, dynamic> f, FwTokens t) =>
      Row(children: [
        VerdictDot(f['severity'] == 'high' ? 'drift' : 'pending'),
        const SizedBox(width: FwLayout.s2),
        Expanded(
          child: Text('${f['path'] ?? ''}:${f['line'] ?? ''}',
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 12, color: t.ink)),
        ),
        const SizedBox(width: FwLayout.s3),
        Text('${f['rule_id'] ?? ''}',
            style: TextStyle(fontSize: 12, color: t.inkMuted)),
      ]);
}

int _int(Object? value) => value is num ? value.toInt() : 0;

Map<String, dynamic>? _asMap(Object? value) => value is Map
    ? value.map((k, v) => MapEntry(k.toString(), v))
    : null;
