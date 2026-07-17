// The turn scaffold rendered: frozen sources read as verified provenance,
// degraded sources are named with their reasons (never hidden), and the
// turn receipt hash is visible. An empty scaffold renders nothing.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/fw.dart';
import 'package:flywheel_desktop/widgets/scaffold_strip.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

TurnScaffold _sample() => TurnScaffold.fromJson({
      'prompt_sha256': 'p' * 64,
      'answer_sha256': 'a' * 64,
      'sources_frozen': [
        {'url': 'https://example.org', 'sha256': 'f' * 64},
      ],
      'degraded': [
        {'url': 'https://dead.example', 'reason': 'ConnectionError: nope'},
      ],
      'eid': 'e1d2c3b4a5f6e1d2c3b4a5f6',
      'chain_hash': 'c' * 64,
    });

void main() {
  testWidgets('frozen and degraded sources both render, named',
      (tester) async {
    await tester.pumpWidget(_wrap(ScaffoldStrip(_sample())));
    expect(find.textContaining('example.org'), findsOneWidget);
    expect(find.textContaining('dead.example'), findsOneWidget);
    expect(find.textContaining('ConnectionError'), findsOneWidget);
    expect(find.textContaining('ffffffff'), findsOneWidget);
  });

  testWidgets('the turn receipt hash is visible', (tester) async {
    await tester.pumpWidget(_wrap(ScaffoldStrip(_sample())));
    expect(find.textContaining('e1d2c3b4'), findsOneWidget);
  });

  testWidgets('a frozen source is provenance, not a verified verdict',
      (tester) async {
    // A frozen source carries only url + sha256, captured BEFORE the answer
    // existed. That is provenance, not an engine verdict, so it must not wear
    // the verified accept color; the only verdict dot here is the degraded
    // source's honest unverifiable.
    await tester.pumpWidget(_wrap(ScaffoldStrip(_sample())));
    final dots = tester
        .widgetList<VerdictDot>(find.byType(VerdictDot))
        .map((d) => d.status)
        .toList();
    expect(dots, isNot(contains('verified')));
  });

  testWidgets('a null or empty scaffold renders nothing', (tester) async {
    await tester.pumpWidget(_wrap(const ScaffoldStrip(null)));
    expect(find.byType(Text), findsNothing);
    final empty = TurnScaffold.fromJson(const {});
    await tester.pumpWidget(_wrap(ScaffoldStrip(empty)));
    expect(find.byType(Text), findsNothing);
  });

  test('CompanionResult parses its scaffold defensively', () {
    final r = CompanionResult.fromJson({
      'source': 'local-verified',
      'text': 'ok',
      'scaffold': {
        'sources_frozen': [
          {'url': 'https://x.example', 'sha256': 'd' * 64}
        ],
        'eid': 'abc',
      },
    });
    expect(r.scaffold, isNotNull);
    expect(r.scaffold!.sourcesFrozen.single.url, 'https://x.example');
    expect(r.scaffold!.eid, 'abc');
    final bare = CompanionResult.fromJson(const {'source': 'cache'});
    expect(bare.scaffold, isNull);
  });
}
