// lint_view.dart — the Lint surface: a native, integrated linter over a
// registered project. Every finding carries a receipt hash and the run
// carries a root hash, so the result re-checks. A finding can hand off to
// the workspace agent as a scoped fix goal.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class LintView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const LintView({super.key, required this.client, required this.alive});

  @override
  State<LintView> createState() => _LintViewState();
}

class _LintViewState extends State<LintView> {
  List<Map<String, dynamic>> _projects = [];
  List<EndpointRow> _endpoints = [];
  String? _root;
  String? _endpoint;
  Map<String, dynamic>? _result;
  bool _linting = false;
  String? _error;
  final Map<String, String> _fixing = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(LintView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  Future<void> _load() async {
    if (!widget.alive) return;
    try {
      final results = await Future.wait(
          [widget.client.projects(), widget.client.endpointRoster()]);
      if (mounted) {
        setState(() {
          _projects = ((results[0] as Map<String, dynamic>)['projects'] ?? [])
              .whereType<Map<String, dynamic>>()
              .toList()
              .cast<Map<String, dynamic>>();
          _endpoints = results[1] as List<EndpointRow>;
          _root ??= _projects.isNotEmpty ? '${_projects.first['root']}' : null;
          _endpoint ??= _endpoints.isNotEmpty ? _endpoints.first.name : null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _lint() async {
    if (_root == null || _linting) return;
    setState(() {
      _linting = true;
      _result = null;
      _error = null;
    });
    try {
      final r = await widget.client.lintProject(_root!);
      if (mounted) setState(() => _result = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _linting = false);
    }
  }

  Future<void> _fix(Map<String, dynamic> f) async {
    if (_endpoint == null || _root == null) return;
    final key = '${f['receipt']}';
    setState(() => _fixing[key] = 'fixing…');
    final goal = 'Fix this lint finding in ${f['file']} at line ${f['line']}: '
        '${f['rule']}: ${f['message']}. Make the smallest correct change.';
    try {
      final r = await widget.client.agent(goal, _endpoint!,
          maxSteps: 8, allowWrite: true, root: _root);
      final clean = (r['integrity'] is Map)
          ? (r['integrity']['clean'] == true)
          : null;
      setState(() => _fixing[key] = r['error'] != null
          ? 'failed: ${r['error']}'
          : 'done · ${r['steps'] ?? '?'} steps'
              '${clean == false ? ' · integrity flagged' : ''}');
    } catch (e) {
      setState(() => _fixing[key] = 'failed: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty('The engine is offline. Lint appears when it runs.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(
      children: [
        const SectionHeader('Lint', kicker: 'findings you can re-check'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'A native linter over your project: the operator quality gates plus '
          'security-relevant patterns. Every finding is content-addressed and '
          'the run carries a root hash, so a clean result is a receipt, not a '
          'claim. A finding can hand off to the workspace agent to fix.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull(_error!),
        ],
        const SizedBox(height: FwLayout.s4),
        HairlineCard(
          child: Wrap(
            spacing: FwLayout.s4,
            runSpacing: FwLayout.s2,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              _picker(t, 'project', _root,
                  {for (final p in _projects) '${p['root']}': '${p['name']}'},
                  (v) => setState(() => _root = v)),
              _picker(t, 'fix via', _endpoint,
                  {for (final e in _endpoints) e.name: e.name},
                  (v) => setState(() => _endpoint = v)),
              FilledButton(
                  onPressed: _linting ? null : _lint,
                  child: Text(_linting ? 'Linting…' : 'Lint project')),
            ],
          ),
        ),
        if (_result != null) ...[
          const SizedBox(height: FwLayout.s4),
          _summary(t, _result!),
          const SizedBox(height: FwLayout.s4),
          ..._findings(t, _result!),
        ],
      ],
    );
  }

  Widget _picker(FwTokens t, String label, String? value,
      Map<String, String> options, ValueChanged<String?> onChanged) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Kicker(label),
        const SizedBox(width: FwLayout.s2),
        DropdownButton<String>(
          value: options.containsKey(value) ? value : null,
          underline: const SizedBox(),
          style: fwMono(t, size: 12, color: t.inkSoft),
          items: [
            for (final e in options.entries)
              DropdownMenuItem(value: e.key, child: Text(e.value)),
          ],
          onChanged: onChanged,
        ),
      ],
    );
  }

  Widget _summary(FwTokens t, Map<String, dynamic> r) {
    final sev = (r['by_severity'] ?? {}) as Map;
    final n = r['n_findings'] ?? 0;
    return Column(
      children: [
        Row(
          children: [
            Expanded(
                child: StatTile(
                    label: 'files', value: '${r['files_scanned'] ?? 0}')),
            const SizedBox(width: FwLayout.s3),
            Expanded(
                child: StatTile(
                    label: 'findings',
                    value: '$n',
                    status: n == 0 ? 'verified' : 'drift')),
            const SizedBox(width: FwLayout.s3),
            Expanded(
                child: StatTile(
                    label: 'high', value: '${sev['high'] ?? 0}', status: 'drift')),
          ],
        ),
        const SizedBox(height: FwLayout.s3),
        if ('${r['root_hash'] ?? ''}'.isNotEmpty)
          HairlineCard(
            child: Row(children: [
              HashText('run', '${r['root_hash']}', keep: 32),
              const Spacer(),
              if (n == 0)
                const VerdictPill('clean', status: 'verified')
              else
                Text('${r['note'] ?? ''}',
                    style: fwMono(t, size: 10.5, color: t.inkFaint)),
            ]),
          ),
      ],
    );
  }

  List<Widget> _findings(FwTokens t, Map<String, dynamic> r) {
    final items = (r['findings'] is List)
        ? (r['findings'] as List).whereType<Map<String, dynamic>>().toList()
        : <Map<String, dynamic>>[];
    if (items.isEmpty) {
      return [
        const HonestNull('No findings. The clean result is receipted above.')
      ];
    }
    return [
      for (final f in items)
        Padding(
          padding: const EdgeInsets.only(bottom: FwLayout.s2),
          child: HairlineCard(
            padding: const EdgeInsets.symmetric(
                horizontal: FwLayout.s3, vertical: FwLayout.s2),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                VerdictPill('${f['severity']}',
                    status: '${f['severity']}' == 'high'
                        ? 'drift'
                        : '${f['severity']}' == 'medium'
                            ? 'unverifiable'
                            : 'verified'),
                const SizedBox(width: FwLayout.s3),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${f['file']}:${f['line']}  ·  ${f['rule']}',
                          style: fwMono(t, size: 11.5, weight: FontWeight.w600)),
                      Text('${f['message']}',
                          style: TextStyle(fontSize: 12, color: t.inkMuted)),
                      Row(children: [
                        Text('receipt ${f['receipt']}',
                            style: fwMono(t, size: 10, color: t.inkFaint)),
                        if (_fixing['${f['receipt']}'] != null) ...[
                          const SizedBox(width: FwLayout.s3),
                          Text('${_fixing['${f['receipt']}']}',
                              style: fwMono(t, size: 10, color: t.drift)),
                        ],
                      ]),
                    ],
                  ),
                ),
                const SizedBox(width: FwLayout.s2),
                OutlinedButton(
                  onPressed: _fixing['${f['receipt']}'] == 'fixing…'
                      ? null
                      : () => _fix(f),
                  child: const Text('Fix'),
                ),
              ],
            ),
          ),
        ),
    ];
  }
}
