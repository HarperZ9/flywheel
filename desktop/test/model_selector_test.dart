// The model selector does what the roster promises: it renders the listed
// models, labels the endpoint default, fires a selection, degrades to the
// honest reason when the listing is unreachable, and never blocks a send.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/model_selector.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: Center(child: child)),
    );

Map<String, dynamic> _roster() => {
      'endpoint': 'ollama',
      'models': [
        {'id': 'telos-coder-14b', 'default': 'true'},
        {'id': 'qwen3:8b', 'default': 'false'},
      ],
      'reason': '',
    };

void main() {
  testWidgets('renders the roster and labels the default', (tester) async {
    await tester.pumpWidget(_wrap(ModelSelectorButton(
      loadModels: () async => _roster(),
      current: null,
      onSelect: (_) {},
    )));
    expect(find.text('default model'), findsOneWidget); // no override yet
    await tester.tap(find.byType(OutlinedButton));
    await tester.pumpAndSettle();
    expect(find.text('telos-coder-14b'), findsOneWidget);
    expect(find.text('qwen3:8b'), findsOneWidget);
    expect(find.text('default'), findsOneWidget); // the flagged entry is labeled
  });

  testWidgets('selection fires with the picked id', (tester) async {
    String? picked;
    await tester.pumpWidget(_wrap(ModelSelectorButton(
      loadModels: () async => _roster(),
      current: null,
      onSelect: (v) => picked = v,
    )));
    await tester.tap(find.byType(OutlinedButton));
    await tester.pumpAndSettle();
    await tester.tap(find.text('qwen3:8b'));
    await tester.pumpAndSettle();
    expect(picked, 'qwen3:8b');
    expect(find.byType(Dialog), findsNothing); // picker closed on selection
  });

  testWidgets('picking the default clears the override', (tester) async {
    String? picked;
    await tester.pumpWidget(_wrap(ModelSelectorButton(
      loadModels: () async => _roster(),
      current: 'qwen3:8b',
      onSelect: (v) => picked = v,
    )));
    expect(find.text('qwen3:8b'), findsOneWidget); // the override shows
    await tester.tap(find.byType(OutlinedButton));
    await tester.pumpAndSettle();
    await tester.tap(find.text('telos-coder-14b'));
    await tester.pumpAndSettle();
    expect(picked, ''); // '' = "use the endpoint default", no model field sent
  });

  testWidgets('an honest reason from the roster stays visible', (tester) async {
    await tester.pumpWidget(_wrap(ModelSelectorButton(
      loadModels: () async => {
        'endpoint': 'openai',
        'models': [
          {'id': 'gpt-4o-mini', 'default': 'true'},
        ],
        'reason': 'credential absent',
      },
      current: null,
      onSelect: (_) {},
    )));
    await tester.tap(find.byType(OutlinedButton));
    await tester.pumpAndSettle();
    expect(find.textContaining('credential absent'), findsOneWidget);
    expect(find.text('gpt-4o-mini'), findsOneWidget); // default still offered
  });

  testWidgets('offline listing degrades to a reason and never blocks',
      (tester) async {
    await tester.pumpWidget(_wrap(ModelSelectorButton(
      loadModels: () async => throw Exception('engine offline'),
      current: null,
      onSelect: (_) {},
    )));
    await tester.tap(find.byType(OutlinedButton));
    await tester.pumpAndSettle();
    expect(find.textContaining('model listing unavailable'), findsOneWidget);
    // the endpoint default row stays selectable: sending is never blocked
    expect(find.text('endpoint default'), findsOneWidget);
    await tester.tap(find.text('endpoint default'));
    await tester.pumpAndSettle();
    expect(find.byType(Dialog), findsNothing);
  });
}
