// uplift_view.dart — the Uplift surface: does the wrapper measurably lift
// the model? Paired arms with intervals, rendered exactly as the engine
// scored them. A separated interval is verified; an interval containing
// zero renders as the honest null it is. Overhead is shown because the
// wrapper costs time; hiding it would be lying by omission.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/uplift_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class UpliftView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const UpliftView({super.key, required this.client, required this.alive});

  @override
  State<UpliftView> createState() => _UpliftViewState();
}

class _UpliftViewState extends State<UpliftView> {
  UpliftSummary? _summary;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(UpliftView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  Future<void> _load() async {
    if (!widget.alive) return;
    try {
      final s = UpliftSummary.fromJson(await widget.client.upliftSummary());
      if (mounted) {
        setState(() {
          _summary = s;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. Uplift runs appear when it runs.',
          command: 'flywheel up');
    }
    final t = context.fw;
    final s = _summary;
    return ViewScroll(
      children: [
        SectionHeader('Uplift',
            kicker: 'bare vs wrapped, intervals or nothing',
            trailing: OutlinedButton(
                onPressed: _load, child: const Text('Refresh'))),
        const SizedBox(height: FwLayout.s3),
        Text(
          'The same task set through the same model twice: bare single-shot '
          'vs the verified loop where only an external oracle accepts. The '
          'delta carries an interval; an interval containing zero is the '
          'honest null, reported as loudly as a win.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s4),
        if (_error != null) HonestNull('Failed: $_error'),
        if (s != null && s.runs.isEmpty)
          HonestNull(
              '${s.note.isEmpty ? "No uplift bench artifact yet." : s.note} '
              'Fire one: python scripts/run_uplift_live.py'),
        if (s?.latest != null) ..._latest(t, s!.latest!),
        if (s != null && s.runs.length > 1) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('all persisted runs'),
          const SizedBox(height: FwLayout.s3),
          HairlineCard(
            child: Column(children: [
              for (final r in s.runs)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(children: [
                    Expanded(
                        child: Text(r['comparison_key']?.toString() ?? '',
                            style: fwMono(t, size: 11.5))),
                    Text((r['providers'] as List?)?.join(', ') ?? '',
                        style: fwMono(t, size: 11, color: t.inkMuted)),
                  ]),
                ),
            ]),
          ),
        ],
      ],
    );
  }

  List<Widget> _latest(FwTokens t, UpliftRun run) {
    return [
      Kicker('latest · ${run.comparisonKey} · '
          'best-of-${run.nCandidates} wrapped arm', hot: true),
      const SizedBox(height: FwLayout.s3),
      for (final d in run.deltas) ...[
        HairlineCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Expanded(
                    child: Text(d.provider,
                        style: Theme.of(context).textTheme.titleMedium)),
                VerdictPill(
                    d.includesZero ? 'no uplift claimed' : 'uplift measured',
                    status: d.verdict),
              ]),
              const SizedBox(height: FwLayout.s2),
              Text(
                  'uplift ${(d.uplift * 100).toStringAsFixed(0)}% · 95% '
                  '[${d.lo.toStringAsFixed(3)}, ${d.hi.toStringAsFixed(3)}] '
                  '· latency overhead '
                  '${(d.latencyOverheadMs / 1000).toStringAsFixed(1)}s',
                  style: fwMono(t, size: 12, color: t.inkSoft)),
              const SizedBox(height: FwLayout.s3),
              for (final r in run.rows.where((r) => r.provider == d.provider))
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(children: [
                    SizedBox(
                        width: 70,
                        child: Text(r.arm,
                            style: fwMono(t, size: 11.5,
                                color: t.inkMuted))),
                    Expanded(
                      child: Text(
                          '${r.passes}/${r.graded} '
                          '(${(r.passRate * 100).toStringAsFixed(0)}%) '
                          '[${r.wilsonLo.toStringAsFixed(3)}, '
                          '${r.wilsonHi.toStringAsFixed(3)}] · '
                          'lat ${(r.latencyMsMean / 1000).toStringAsFixed(1)}s '
                          '· cand ${r.candidatesMean.toStringAsFixed(2)}'
                          '${r.unverifiable > 0 ? ' · unver ${r.unverifiable}' : ''}',
                          style: fwMono(t, size: 11.5)),
                    ),
                  ]),
                ),
            ],
          ),
        ),
        const SizedBox(height: FwLayout.s3),
      ],
    ];
  }
}
