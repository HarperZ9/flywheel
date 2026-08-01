// discourse_cards.dart — the card renderers for the Discourse destination.
//
// Sentiment and contestedness are WEIGHTS, never verdicts, so they render in
// neutral ink; the single verdict mark in the destination is the receipt's
// verify status, drawn elsewhere. Kept out of the view file so each stays small
// and each card is widget-testable on its own.

import 'package:flutter/material.dart';

import '../models/discourse.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

String _pct(double v) => '${(v * 100).round()}%';

/// The topics the corpus is genuinely split on, measured across every comment
/// that mentions a term (immune to the lexical clustering that would file
/// agreement and disagreement under different themes).
Widget contestedSection(BuildContext context, DiscourseDigest d) {
  final fw = context.fw;
  return HairlineCard(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (int i = 0; i < d.contested.length; i++) ...[
          if (i > 0) const SizedBox(height: FwLayout.s2),
          Row(children: [
            Expanded(
              child: Text(d.contested[i].term,
                  style: fwMono(fw, size: 12.5, color: fw.ink),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
            ),
            const SizedBox(width: FwLayout.s2),
            Text(
              '${d.contested[i].mentions} voices   ·   '
              '+${_pct(d.contested[i].posShare)} / -${_pct(d.contested[i].negShare)}'
              '   ·   split ${d.contested[i].score.toStringAsFixed(2)}',
              style: fwMono(fw, size: 11.5, color: fw.inkSoft),
            ),
          ]),
        ],
      ],
    ),
  );
}

/// One theme: its label, size and weight, its sentiment split, its controversy
/// (how divided the theme is), and the single highest-weight dissenting voice.
Widget discourseThemeCard(BuildContext context, DiscourseTheme t) {
  final fw = context.fw;
  final mean = t.meanCompound >= 0
      ? '+${t.meanCompound.toStringAsFixed(2)}'
      : t.meanCompound.toStringAsFixed(2);
  return HairlineCard(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          Expanded(
            child: Text(t.label,
                style: Theme.of(context).textTheme.titleMedium,
                maxLines: 2,
                overflow: TextOverflow.ellipsis),
          ),
          const SizedBox(width: FwLayout.s2),
          Text('${t.size}  ·  w ${t.weightedScore.toStringAsFixed(1)}',
              style: fwMono(fw, size: 12, color: fw.inkFaint)),
        ]),
        const SizedBox(height: FwLayout.s2),
        // Sentiment and controversy are WEIGHTS, not verdicts: neutral ink only,
        // never the verified/drift palette.
        Text(
          'positive ${_pct(t.posShare)}   ·   neutral ${_pct(t.neuShare)}   ·   '
          'negative ${_pct(t.negShare)}   ·   mean $mean',
          style: fwMono(fw, size: 12, color: fw.inkSoft),
        ),
        const SizedBox(height: FwLayout.s2),
        Text('controversy ${t.controversy.toStringAsFixed(2)}',
            style: fwMono(fw, size: 11.5, color: fw.inkMuted)),
        if (t.dissent != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text('dissent: ${t.dissent}',
              style: fwMono(fw, size: 11.5, color: fw.inkMuted)),
        ],
      ],
    ),
  );
}
