// endpoint_details.dart — the provider roster and routing scoreboard,
// extracted from endpoints_view so the view stays under 300 lines.

import 'package:flutter/material.dart';

import '../models/endpoint_models.dart';
import '../models/endpoint_row.dart';
import '../theme/flywheel_theme.dart';
import 'charts.dart';
import 'fw.dart';

/// Sorted list of configured providers with credential presence.
class ProviderRoster extends StatelessWidget {
  final List<EndpointRow> roster;
  const ProviderRoster({super.key, required this.roster});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final sorted = roster.toList()
      ..sort((a, b) => endpointRank(a).compareTo(endpointRank(b)));
    return HairlineCard(
      padding: const EdgeInsets.symmetric(
          horizontal: FwLayout.s4, vertical: FwLayout.s2),
      child: Column(children: [for (final r in sorted) _row(t, r)]),
    );
  }

  Widget _row(FwTokens t, EndpointRow r) {
    final (label, status) = switch (r.credential) {
      'present' => ('key present', 'verified'),
      'cli-auth' => ('subscription', 'verified'),
      'local-none' => ('local', 'verified'),
      _ => ('no key', 'absent'),
    };
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2 + 2),
      decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        children: [
          Expanded(
            flex: 3,
            child: Text(r.name,
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 12, weight: FontWeight.w600)),
          ),
          const SizedBox(width: FwLayout.s3),
          Expanded(
            flex: 4,
            child: Text(
                r.providerRole.isNotEmpty ? r.providerRole : r.backend,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 12, color: t.inkMuted)),
          ),
          const SizedBox(width: FwLayout.s3),
          VerdictPill(label, status: status),
        ],
      ),
    );
  }
}

/// Observed routing outcomes with success rates and latency.
class EndpointScoreboard extends StatelessWidget {
  final List<ProviderScore> scores;
  const EndpointScoreboard({super.key, required this.scores});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    if (scores.isEmpty) {
      return const HonestNull(
          'No routed traffic recorded yet. The scoreboard fills from '
          'real outcomes as prompts route; nothing here is a promise.');
    }
    return LayoutBuilder(builder: (context, box) {
      final card = HairlineCard(
        padding: const EdgeInsets.symmetric(
            horizontal: FwLayout.s4, vertical: FwLayout.s2),
        child: Column(
          children: [for (final s in scores) _scoreRow(t, s)],
        ),
      );
      if (box.maxWidth >= 560) return card;
      return SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: SizedBox(width: 560, child: card),
      );
    });
  }

  Widget _scoreRow(FwTokens t, ProviderScore s) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2 + 2),
      decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        children: [
          SizedBox(
            width: 170,
            child: Text(s.name,
                style: fwMono(t, size: 12, weight: FontWeight.w600)),
          ),
          _cell(t, '${s.attempts} tried'),
          MiniBar(s.successRate,
              status: s.successRate >= 0.5 ? 'verified' : 'drift'),
          const SizedBox(width: FwLayout.s3),
          _cell(t, '${(s.successRate * 100).toStringAsFixed(0)}% ok'),
          _cell(t, '${s.meanLatency.toStringAsFixed(1)}s'),
          const Spacer(),
          if (s.circuitOpen)
            const VerdictPill('circuit open', status: 'drift')
          else
            Text('score ${s.score.toStringAsFixed(2)}',
                style: fwMono(t, size: 11, color: t.inkMuted)),
        ],
      ),
    );
  }

  Widget _cell(FwTokens t, String text) => SizedBox(
        width: 90,
        child: Text(text, style: fwMono(t, size: 11.5, color: t.inkMuted)),
      );
}
