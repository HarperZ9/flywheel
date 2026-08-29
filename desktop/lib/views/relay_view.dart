import 'dart:async';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class RelayView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const RelayView({super.key, required this.client, required this.alive});

  @override
  State<RelayView> createState() => _RelayViewState();
}

class _RelayViewState extends State<RelayView> {
  List<Map<String, dynamic>> _runs = [];
  List<Map<String, dynamic>> _sessions = [];
  bool _loading = true;
  String? _error;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _load();
    _poll = Timer.periodic(const Duration(seconds: 10), (_) => _load());
  }

  @override
  void didUpdateWidget(RelayView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    if (!widget.alive) return;
    try {
      final runsDoc = await widget.client.relayRuns();
      final sessDoc = await widget.client.relaySessions();
      if (!mounted) return;
      setState(() {
        _runs = _listOf(runsDoc['runs']);
        _sessions = _listOf(sessDoc['sessions']);
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  static List<Map<String, dynamic>> _listOf(Object? v) =>
      (v is List ? v.whereType<Map<String, dynamic>>().toList() : const []);

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. Relay appears when it runs.',
          command: 'flywheel up');
    }
    if (_loading && _runs.isEmpty) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2));
    }
    return ViewScroll(children: [
      SectionHeader('Relay',
          kicker: 'coding agent + remote access',
          trailing: OutlinedButton(
              onPressed: _load, child: const Text('Refresh'))),
      const SizedBox(height: FwLayout.s3),
      if (_error != null) ...[
        HonestNull('Could not reach relay: $_error'),
        const SizedBox(height: FwLayout.s4),
      ],
      _RunsSection(runs: _runs, client: widget.client),
      const SizedBox(height: FwLayout.s6),
      _SessionsSection(sessions: _sessions),
    ]);
  }
}

class _RunsSection extends StatelessWidget {
  final List<Map<String, dynamic>> runs;
  final GatewayClient client;
  const _RunsSection({required this.runs, required this.client});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Agent runs',
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
      const SizedBox(height: FwLayout.s2),
      if (runs.isEmpty)
        const HonestNull('No relay runs recorded yet. Start one from Chat '
            'with agent mode, or from the CLI with `flywheel relay`.'),
      for (final run in runs) ...[
        const SizedBox(height: FwLayout.s2),
        _RunCard(run: run, t: t, client: client),
      ],
    ]);
  }
}

class _RunCard extends StatelessWidget {
  final Map<String, dynamic> run;
  final FwTokens t;
  final GatewayClient client;
  const _RunCard({required this.run, required this.t, required this.client});

  @override
  Widget build(BuildContext context) {
    final runId = '${run['run_id'] ?? ''}';
    final status = '${run['status'] ?? 'unknown'}';
    final goal = '${run['goal'] ?? ''}';
    final steps = run['steps'];
    final stepsText = steps is int ? '$steps steps' : '';
    final verdict = _verdictStatus(status);
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          VerdictDot(verdict, size: 8),
          const SizedBox(width: FwLayout.s2),
          VerdictPill(status, status: verdict),
          const Spacer(),
          if (runId.isNotEmpty)
            HashText('run', runId, keep: 12),
        ]),
        if (goal.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Text(goal, maxLines: 2, overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 13, color: t.ink)),
        ],
        if (stepsText.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s1),
          Text(stepsText, style: fwMono(t, size: 11, color: t.inkFaint)),
        ],
      ]),
    );
  }

  static String _verdictStatus(String status) {
    final s = status.toLowerCase();
    if (s == 'done' || s == 'complete' || s == 'completed') return 'verified';
    if (s == 'running' || s == 'in_progress') return 'live';
    if (s == 'failed' || s == 'error') return 'drift';
    return 'unverifiable';
  }
}

class _SessionsSection extends StatelessWidget {
  final List<Map<String, dynamic>> sessions;
  const _SessionsSection({required this.sessions});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Session ledgers',
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
      const SizedBox(height: FwLayout.s2),
      if (sessions.isEmpty)
        const HonestNull('No saved sessions. Each relay run writes a '
            'hash-chained ledger that re-verifies offline.'),
      for (final sess in sessions) ...[
        const SizedBox(height: FwLayout.s2),
        _SessionCard(session: sess, t: t),
      ],
    ]);
  }
}

class _SessionCard extends StatelessWidget {
  final Map<String, dynamic> session;
  final FwTokens t;
  const _SessionCard({required this.session, required this.t});

  @override
  Widget build(BuildContext context) {
    final path = '${session['path'] ?? ''}';
    final entries = session['entries'];
    final entriesText = entries is int ? '$entries entries' : '';
    final root = '${session['root'] ?? ''}';
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (path.isNotEmpty)
          Text(path.split('/').last.split('\\').last,
              style: fwMono(t, size: 12, color: t.ink),
              maxLines: 1, overflow: TextOverflow.ellipsis),
        const SizedBox(height: FwLayout.s1),
        Row(children: [
          if (entriesText.isNotEmpty)
            Text(entriesText, style: fwMono(t, size: 11, color: t.inkFaint)),
          if (root.isNotEmpty) ...[
            const SizedBox(width: FwLayout.s3),
            Expanded(child: HashText('root', root, keep: 16)),
          ],
        ]),
      ]),
    );
  }
}
