// science_view.dart — the Science workbench: ask, gather evidence with
// provenance, get the question priced as a research spec, and put stated
// claims to witnessed judgment. The load-bearing rule renders plainly:
// an unmeasured claim is UNVERIFIABLE, and it stays that way until a
// measurement exists. The model proposes; the instruments dispose.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/science_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/plan_cards.dart';
import '../widgets/science_history.dart';

class ScienceView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const ScienceView({super.key, required this.client, required this.alive});

  @override
  State<ScienceView> createState() => _ScienceViewState();
}

class _Claim {
  final text = TextEditingController();
  final falsification = TextEditingController();
  void dispose() {
    text.dispose();
    falsification.dispose();
  }
}

class _ScienceViewState extends State<ScienceView> {
  final _question = TextEditingController();
  final List<_Claim> _claims = [];
  bool _running = false;
  ScienceRun? _run;
  bool? _storedOk; // chain re-check when _run came from history
  List<Map<String, dynamic>> _history = [];
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadHistory();
  }

  @override
  void didUpdateWidget(ScienceView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _loadHistory();
  }

  Future<void> _loadHistory() async {
    if (!widget.alive) return;
    try {
      final r = await widget.client.scienceRuns(limit: 20);
      if (mounted) {
        setState(() => _history = ((r['runs'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .toList());
      }
    } catch (_) {/* run errors already surface below the composer */}
  }

  Future<void> _openStored(Map<String, dynamic> row) async {
    final chain = '${row['chain_hash'] ?? ''}';
    if (chain.length < 4) return;
    try {
      final doc = await widget.client.scienceRunDetail(chain);
      if (mounted) {
        setState(() {
          _run = ScienceRun.fromJson(doc);
          _storedOk = doc['chain_ok'] == true;
          // the stored question lands in the composer, so one tap re-runs
          // it fresh against today's sources
          _question.text = '${doc['question'] ?? row['question'] ?? ''}';
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  @override
  void dispose() {
    _question.dispose();
    for (final c in _claims) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _runScience() async {
    final q = _question.text.trim();
    if (q.isEmpty || _running) return;
    setState(() {
      _running = true;
      _run = null;
      _error = null;
    });
    try {
      final claims = [
        for (final (i, c) in _claims.indexed)
          if (c.text.text.trim().isNotEmpty)
            {
              'id': 'c${i + 1}',
              'text': c.text.text.trim(),
              'falsification': c.falsification.text.trim(),
            }
      ];
      final r = ScienceRun.fromJson(
          await widget.client.science(q, claims: claims));
      if (mounted) {
        setState(() {
          _run = r;
          _storedOk = null; // a live run, not a re-read receipt
        });
      }
      _loadHistory(); // the run just persisted; history shows it now
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. Science runs appear when it runs.',
          command: 'flywheel up');
    }
    final t = context.fw;
    final r = _run;
    return ViewScroll(
      children: [
        const SectionHeader('Science',
            kicker: 'evidence, spec, judgment, one chain'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'Ask a question: gather brings sources with provenance, the forge '
          'prices it as a research spec, and crucible judges your stated '
          'claims. An unmeasured claim comes back UNVERIFIABLE and stays '
          'that way; the instruments dispose, never the model.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s4),
        _composer(t),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull('Failed: $_error'),
        ],
        if (_storedOk == false) ...[
          const SizedBox(height: FwLayout.s3),
          const HonestNull(
              'This stored run failed re-verification: its content no '
              'longer matches its chain hash. It is served as TAMPERED.'),
        ],
        if (r != null) ..._result(t, r),
        if (_history.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s5),
          Kicker('history · ${_history.length} stored '
              'run${_history.length == 1 ? '' : 's'}, re-verified at read'),
          const SizedBox(height: FwLayout.s3),
          ScienceHistoryList(runs: _history, onOpen: _openStored),
        ],
      ],
    );
  }

  Widget _composer(FwTokens t) {
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _question,
            maxLines: 2,
            minLines: 1,
            style: const TextStyle(fontSize: 13.5),
            decoration: const InputDecoration(
                hintText: 'The research question…'),
          ),
          const SizedBox(height: FwLayout.s3),
          for (final (i, c) in _claims.indexed) ...[
            Row(children: [
              Text('c${i + 1}', style: fwMono(t, size: 11, color: t.inkFaint)),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: TextField(
                  controller: c.text,
                  style: const TextStyle(fontSize: 12.5),
                  decoration: const InputDecoration(hintText: 'Claim…'),
                ),
              ),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: TextField(
                  controller: c.falsification,
                  style: const TextStyle(fontSize: 12.5),
                  decoration: const InputDecoration(
                      hintText: 'What would falsify it…'),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.close, size: 14),
                onPressed: () => setState(() {
                  _claims.removeAt(i).dispose();
                }),
              ),
            ]),
            const SizedBox(height: FwLayout.s2),
          ],
          Row(children: [
            OutlinedButton(
              onPressed: () => setState(() => _claims.add(_Claim())),
              child: const Text('Add claim'),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _running ? null : _runScience,
              child: Text(_running ? 'Running…' : 'Run'),
            ),
          ]),
        ],
      ),
    );
  }

  List<Widget> _result(FwTokens t, ScienceRun r) {
    return [
      const SizedBox(height: FwLayout.s4),
      for (final e in r.errors.entries)
        Padding(
          padding: const EdgeInsets.only(bottom: FwLayout.s3),
          child: HonestNull('${e.key} failed: ${e.value}. The rest of the '
              'run continued.'),
        ),
      if (r.sources.isNotEmpty) ...[
        const Kicker('evidence · gather provenance', hot: true),
        const SizedBox(height: FwLayout.s2),
        HairlineCard(
          child: Column(children: [
            for (final s in r.sources)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(children: [
                  Text(s.id, style: fwMono(t, size: 11, color: t.inkFaint)),
                  const SizedBox(width: FwLayout.s3),
                  Expanded(
                      child: Text(s.title,
                          style: TextStyle(
                              fontSize: 12.5, color: t.inkSoft))),
                  SelectableText(s.url,
                      style: fwMono(t, size: 10.5, color: t.inkMuted)),
                ]),
              ),
          ]),
        ),
        const SizedBox(height: FwLayout.s3),
      ],
      if (r.verdicts.isNotEmpty) ...[
        const Kicker('witnessed verdicts'),
        const SizedBox(height: FwLayout.s2),
        HairlineCard(
          child: Column(children: [
            for (final v in r.verdicts)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(children: [
                  VerdictPill(v.status, status: v.verdict),
                  const SizedBox(width: FwLayout.s3),
                  Text(v.claimId, style: fwMono(t, size: 11.5)),
                  const SizedBox(width: FwLayout.s3),
                  Expanded(
                      child: Text(v.grounds,
                          style: TextStyle(
                              fontSize: 12, color: t.inkMuted))),
                ]),
              ),
          ]),
        ),
        const SizedBox(height: FwLayout.s3),
      ],
      if (r.plan != null)
        ForgedPlanCard(plan: r.plan!),
      const SizedBox(height: FwLayout.s3),
      HashText('chain', r.chainHash),
    ];
  }
}
