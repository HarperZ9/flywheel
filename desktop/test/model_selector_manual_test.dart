import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/model_selector.dart';

Future<void> openPicker(
    WidgetTester tester,
    Future<Map<String, dynamic>> Function() loader,
    ValueChanged<String> onSelect) async {
  await tester.pumpWidget(MaterialApp(
    theme: flywheelLightTheme(),
    home: Scaffold(
        body: ModelSelectorButton(
            loadModels: loader, current: 'prior-model', onSelect: onSelect)),
  ));
  await tester.tap(find.byType(OutlinedButton));
  await tester.pumpAndSettle();
}

void main() {
  for (final mode in ['empty', 'error', 'pending']) {
    testWidgets('manual model can be requested with $mode listing',
        (tester) async {
      String? selected;
      final pending = Completer<Map<String, dynamic>>();
      await openPicker(tester, () {
        if (mode == 'pending') return pending.future;
        if (mode == 'error') return Future.error(Exception('offline'));
        return Future.value({'models': [], 'reason': 'listing unavailable'});
      }, (value) => selected = value);
      await tester.enterText(find.byType(TextField), 'gpt-6-astra');
      expect(
          find.textContaining('Availability is not verified'), findsOneWidget);
      await tester.tap(find.text('Use model ID'));
      await tester.pumpAndSettle();
      expect(selected, 'gpt-6-astra');
      expect(find.byType(Dialog), findsNothing);
    });
  }

  testWidgets('default reset is available during pending listing',
      (tester) async {
    String? selected;
    await openPicker(tester, () => Completer<Map<String, dynamic>>().future,
        (value) => selected = value);
    await tester.tap(find.text('Use endpoint default'));
    await tester.pumpAndSettle();
    expect(selected, '');
  });

  testWidgets('unsafe or oversized manual IDs cannot be selected',
      (tester) async {
    String? selected;
    await openPicker(
        tester, () async => {'models': []}, (value) => selected = value);
    for (final value in ['', 'bad model', 'x&whoami', 'x%PATH%', 'a' * 161]) {
      await tester.enterText(find.byType(TextField), value);
      await tester.tap(find.text('Use model ID'));
      await tester.pump();
      expect(selected, isNull);
      expect(find.byType(Dialog), findsOneWidget);
      expect(find.textContaining('Enter a model ID'), findsOneWidget);
    }
  });

  testWidgets('cancel leaves prior selection unchanged', (tester) async {
    String? selected;
    await openPicker(
        tester, () async => {'models': []}, (value) => selected = value);
    await tester.enterText(find.byType(TextField), 'gpt-6-astra');
    await tester.tapAt(const Offset(5, 5));
    await tester.pumpAndSettle();
    expect(selected, isNull);
    expect(find.byType(Dialog), findsNothing);
  });

  testWidgets('manual input fits a constrained dialog and trims spaces',
      (tester) async {
    tester.view.physicalSize = const Size(400, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    String? selected;
    await openPicker(
        tester,
        () async => {'models': [], 'reason': 'listing unavailable'},
        (value) => selected = value);
    await tester.enterText(find.byType(TextField), '  gpt-6-astra  ');
    await tester.tap(find.text('Use model ID'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(selected, 'gpt-6-astra');
  });
}
