// The Discourse card renderers: contestedness and controversy are weights,
// rendered as plain text in neutral ink; nothing here is a verdict.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/discourse.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/discourse_cards.dart';

Future<void> _pump(WidgetTester tester, Widget child) => tester.pumpWidget(
    MaterialApp(theme: flywheelLightTheme(), home: Scaffold(body: child)));

void main() {
  testWidgets('contestedSection lists each split topic with its voices and score',
      (tester) async {
    final d = DiscourseDigest.fromEnvelope({
      'result': {
        'themes': [],
        'contested': [
          {'term': 'battery', 'mentions': 5, 'pos': 0.2, 'neg': 0.6, 'contested': 0.54},
        ],
      },
    });
    await _pump(tester, Builder(builder: (c) => contestedSection(c, d)));
    expect(find.textContaining('battery'), findsOneWidget);
    expect(find.textContaining('5 voices'), findsOneWidget);
    expect(find.textContaining('split 0.54'), findsOneWidget);
  });

  testWidgets('discourseThemeCard shows the controversy score', (tester) async {
    final t = DiscourseTheme.fromJson({
      'label': 'audio',
      'size': 4,
      'weighted_score': 9.0,
      'sentiment': {'pos': 0.5, 'neg': 0.25, 'neu': 0.25, 'mean_compound': 0.1},
      'controversy': 0.62,
      'dissent': 'c3',
    });
    await _pump(tester, Builder(builder: (c) => discourseThemeCard(c, t)));
    expect(find.textContaining('audio'), findsOneWidget);
    expect(find.textContaining('controversy 0.62'), findsOneWidget);
    expect(find.textContaining('dissent: c3'), findsOneWidget);
  });
}
