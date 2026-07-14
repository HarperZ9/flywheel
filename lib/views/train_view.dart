// train_view.dart — the Train workspace: the local-model flywheel harness.
// Watches the verified-inference duel (does the harness beat a model used
// raw?), the closed-loop self-audit, and the training supervisor. Read-only;
// training start stays operator-gated.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/charts.dart';
import '../widgets/fw.dart';
import '../widgets/training_card.dart';

class TrainView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const TrainView({super.key, required this.client, required this.alive});

  @override
  State<TrainView> createState() => _TrainViewState();
}

class _TrainViewState extends State<TrainView> {
  Map<String, dynamic>? _duel;
  Map<String, dynamic>? _training;
  Map<String, dynamic>? _loop;
  bool _auditing = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(TrainView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  Future<void> _load() async {
    if (!widget.alive) return;
    try {
      final results = await Future.wait([
        widget.client.getJson('/api/train/duel'),
        widget.client.trainingStatus(),
      ]);
      if (mounted) {
        setState(() {
          _duel = results[0];
          _training = results[1];
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _audit() async {
    setState(() => _auditing = true);
    try {
      final r = await widget.client.getJson('/api/train/loop');
      if (mounted) setState(() => _loop = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _auditing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. The training harness appears when it runs.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(
      children: [
        const SectionHeader('Train', kicker: 'the local-model flywheel'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'The harness earns correctness, not the weights. The duel measures '
          'it: the same model used raw versus the Flywheel verified loop over '
          'it. Training start stays operator-gated.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull(_error!),
        ],
        const SizedBox(height: FwLayout.s4),
        const Kicker('verified-inference duel', hot: true),
        const SizedBox(height: FwLayout.s3),
        _duelPanel(t),
        if (_training != null && _training!['error'] == null) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('training supervisor · read-only'),
          const SizedBox(height: FwLayout.s3),
          TrainingCard(training: _training!),
        ],
        const SizedBox(height: FwLayout.s5),
        Row(
          children: [
            const Kicker('closed-loop audit'),
            const Spacer(),
            OutlinedButton(
              onPressed: _auditing ? null : _audit,
              child: Text(_auditing ? 'Auditing…' : 'Run audit'),
            ),
          ],
        ),
        const SizedBox(height: FwLayout.s3),
        _loopPanel(t),
      ],
    );
  }

  Widget _duelPanel(FwTokens t) {
    final d = _duel;
    if (d == null) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2));
    }
    if (d['status'] == 'none') {
      return HonestNull('${d['note'] ?? 'No duel has been run yet.'}');
    }
    final single = ((d['single_rate'] ?? 0) as num).toDouble();
    final verified = ((d['verified_rate'] ?? 0) as num).toDouble();
    final lift = ((d['harness_lift'] ?? 0) as num).toDouble();
    final rescued = (d['rescued'] is List) ? (d['rescued'] as List) : const [];
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              VerdictPill('${d['status']}',
                  status: d['status'] == 'complete' ? 'verified' : 'unverifiable'),
              const SizedBox(width: FwLayout.s2),
              Text('${d['source'] ?? ''} · ${d['n_tasks'] ?? 0} tasks',
                  style: fwMono(t, size: 10.5, color: t.inkFaint)),
            ],
          ),
          const SizedBox(height: FwLayout.s3),
          _arm(t, 'raw single-shot', single, 'drift'),
          const SizedBox(height: FwLayout.s2),
          _arm(t, 'Flywheel verified', verified, 'verified'),
          const SizedBox(height: FwLayout.s3),
          Row(
            children: [
              VerdictPill(
                  'harness lift ${lift >= 0 ? '+' : ''}${(lift * 100).toStringAsFixed(0)} pts',
                  status: lift > 0 ? 'verified' : 'drift'),
              const SizedBox(width: FwLayout.s3),
              if (rescued.isNotEmpty)
                Expanded(
                  child: Text('rescued: ${rescued.join(', ')}',
                      overflow: TextOverflow.ellipsis,
                      style: fwMono(t, size: 11, color: t.inkMuted)),
                ),
            ],
          ),
          const SizedBox(height: FwLayout.s2),
          Text('${d['note'] ?? ''}',
              style: TextStyle(fontSize: 11, color: t.inkFaint, height: 1.4)),
        ],
      ),
    );
  }

  Widget _arm(FwTokens t, String label, double rate, String status) {
    return Row(
      children: [
        SizedBox(
            width: 140,
            child: Text(label, style: fwMono(t, size: 12, color: t.inkSoft))),
        Expanded(child: MiniBar(rate, status: status, width: 200)),
        const SizedBox(width: FwLayout.s3),
        Text('${(rate * 100).toStringAsFixed(0)}%',
            style: fwMono(t, size: 12, weight: FontWeight.w600)),
      ],
    );
  }

  Widget _loopPanel(FwTokens t) {
    final l = _loop;
    if (l == null) {
      return HonestNull(
          'The loop-closure audit runs real handoffs; press Run audit to '
          'measure how many of the perceive → verify → memory handoffs close.');
    }
    final closed = l['n_closed'] ?? 0;
    final total = l['n_handoffs'] ?? 0;
    final open = (l['open_links'] is List) ? (l['open_links'] as List) : const [];
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              VerdictPill('$closed/$total closed',
                  status: (l['fully_closed'] == true) ? 'verified' : 'drift'),
              const SizedBox(width: FwLayout.s3),
              Text('${((l['closure_fraction'] ?? 0) as num) * 100}% closure',
                  style: fwMono(t, size: 11, color: t.inkMuted)),
            ],
          ),
          if (open.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            Text('open: ${open.join(', ')}',
                style: fwMono(t, size: 11, color: t.drift)),
          ],
        ],
      ),
    );
  }
}
