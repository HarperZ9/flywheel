import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/chat_composer.dart';

void main() {
  testWidgets('streaming without server control renders no fake Stop',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: ChatComposer(
                streaming: true,
                onDraftChanged: (_) {},
                onSend: (_) async => PromptDisposition.retained,
                onStop: () {}))));

    expect(find.byTooltip('Stop'), findsNothing);
    expect(find.byIcon(Icons.stop_rounded), findsNothing);
  });

  test('Chat and Compare have no local stop that fabricates completion', () {
    for (final path in const [
      'lib/views/agent_view.dart',
      'lib/views/compare_view.dart',
    ]) {
      final source = File(path).readAsStringSync();
      expect(source.contains('void _stop()'), isFalse, reason: path);
      expect(source.contains('onStop: _stop'), isFalse, reason: path);
    }
  });

  test('partial Chat and Compare closure remains explicitly unknown', () {
    final chat = File('lib/views/agent_view.dart').readAsStringSync();
    final compare = File('lib/views/compare_view.dart').readAsStringSync();
    expect(chat.contains('_assistant!.receipt == null'), isTrue);
    expect(compare.contains('assistant.receipt == null'), isTrue);
    expect(chat.contains('completion is unknown'), isTrue);
    expect(compare.contains('completion is unknown'), isTrue);
  });
}
