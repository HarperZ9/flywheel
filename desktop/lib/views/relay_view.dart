import 'dart:async';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/remote_surface.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/relay_panels.dart';
import '../widgets/remote_surface_card.dart';

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
  RemoteSurface _remote = const RemoteSurface();
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
      // Independent reads, so they go together rather than in sequence.
      final docs = await Future.wait([
        widget.client.relayRuns(),
        widget.client.relaySessions(),
        widget.client.relayRemote(),
      ]);
      if (!mounted) return;
      setState(() {
        _runs = _listOf(docs[0]['runs']);
        _sessions = _listOf(docs[1]['sessions']);
        _remote = RemoteSurface.fromJson(docs[2]);
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
      RemoteSurfaceCard(surface: _remote),
      const SizedBox(height: FwLayout.s6),
      _RunsSection(runs: _runs, client: widget.client),
      const SizedBox(height: FwLayout.s6),
      _sessionsSection(context),
    ]);
  }

  Widget _sessionsSection(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Session ledgers',
          style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
      const SizedBox(height: FwLayout.s2),
      if (_sessions.isEmpty)
        const HonestNull('No saved sessions. Each relay run writes a '
            'hash-chained ledger that re-verifies offline.'),
      for (final sess in _sessions) ...[
        const SizedBox(height: FwLayout.s2),
        RelaySessionCard(session: sess),
      ],
    ]);
  }
}

class _RunsSection extends StatelessWidget {
  final List<Map<String, dynamic>> runs;
  final GatewayClient client;
  const _RunsSection({required this.runs, required this.client});

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Agent runs',
          style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
      const SizedBox(height: FwLayout.s2),
      if (runs.isEmpty)
        const HonestNull('No relay runs recorded yet. Start one from Chat '
            'with agent mode, or from the CLI with `flywheel relay`.'),
      for (final run in runs) ...[
        const SizedBox(height: FwLayout.s2),
        _RunCard(run: run, client: client),
      ],
    ]);
  }
}

class _RunCard extends StatefulWidget {
  final Map<String, dynamic> run;
  final GatewayClient client;
  const _RunCard({required this.run, required this.client});

  @override
  State<_RunCard> createState() => _RunCardState();
}

class _RunCardState extends State<_RunCard> {
  bool _expanded = false;
  Map<String, dynamic>? _detail;
  bool _loadingDetail = false;

  String get _runId => '${widget.run['run_id'] ?? ''}';

  Future<void> _loadDetail() async {
    if (_runId.isEmpty || _loadingDetail) return;
    setState(() => _loadingDetail = true);
    try {
      final status = await widget.client.relayStatus(_runId);
      final result = await widget.client.relayResult(_runId);
      if (!mounted) return;
      setState(() {
        _detail = {...status, 'result_doc': result};
        _loadingDetail = false;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _detail = {'error': '$e'};
          _loadingDetail = false;
        });
      }
    }
  }

  void _toggle() {
    setState(() => _expanded = !_expanded);
    if (_expanded && _detail == null) _loadDetail();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final status = '${widget.run['status'] ?? 'unknown'}';
    final goal = '${widget.run['goal'] ?? ''}';
    final steps = widget.run['steps'];
    final stepsText = steps is int ? '$steps steps' : '';
    final verdict = _verdictFor(status);
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        InkWell(
          onTap: _runId.isNotEmpty ? _toggle : null,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                VerdictDot(verdict, size: 8),
                const SizedBox(width: FwLayout.s2),
                VerdictPill(status, status: verdict),
                const Spacer(),
                if (_runId.isNotEmpty) HashText('run', _runId, keep: 12),
              ]),
              if (goal.isNotEmpty) ...[
                const SizedBox(height: FwLayout.s2),
                Text(goal, maxLines: 2, overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 13, color: t.ink)),
              ],
              if (stepsText.isNotEmpty) ...[
                const SizedBox(height: FwLayout.s1),
                Text(stepsText,
                    style: fwMono(t, size: 11, color: t.inkFaint)),
              ],
            ],
          ),
        ),
        if (_expanded) ...[
          Divider(height: FwLayout.s4, color: t.hairline),
          RelayDetailPane(
              detail: _detail, loading: _loadingDetail,
              onRefresh: _loadDetail),
        ],
      ]),
    );
  }

  static String _verdictFor(String status) {
    final s = status.toLowerCase();
    if (s == 'done' || s == 'complete' || s == 'completed') return 'verified';
    if (s == 'running' || s == 'in_progress') return 'live';
    if (s == 'failed' || s == 'error') return 'drift';
    return 'unverifiable';
  }
}
