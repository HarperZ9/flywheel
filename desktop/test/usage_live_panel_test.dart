import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/usage_live_panel.dart';

Map<String, dynamic> snapshot({double? rate = 32.9}) => {
      'schema': 'flywheel.usage-live/v1',
      'observed_utc': '2026-09-17T22:00:00Z',
      'models': [
        {
          'id': 'local-a',
          'model': 'Local model A',
          'endpoint': 'local-a',
          'status': 'observed',
          'source': 'llama.cpp /slots',
          'decode_tokens_per_second': rate,
          'prefill_tokens_per_second': null,
          'generated_tokens': 925743,
          'prompt_tokens': 2170739
        },
        {
          'id': 'local-b',
          'model': 'Local model B',
          'endpoint': 'local-b',
          'status': 'unavailable',
          'source': 'unavailable'
        }
      ]
    };

Widget wrap(Future<Map<String, dynamic>> Function() load, {double scale = 1}) =>
    MaterialApp(
      theme: flywheelLightTheme(),
      builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(scale)),
          child: child!),
      home: Scaffold(
          body: SingleChildScrollView(
              child: UsageLivePanel(
        loadSnapshot: load,
        refreshInterval: const Duration(seconds: 1),
      ))),
    );

void main() {
  testWidgets(
      'pause and resume during an in-flight load never overlap requests',
      (t) async {
    var calls = 0;
    final pending = Completer<Map<String, dynamic>>();
    await t.pumpWidget(wrap(() {
      calls++;
      return pending.future;
    }));
    await t.tap(find.text('Pause'));
    await t.pump();
    await t.tap(find.text('Resume'));
    await t.pump();
    expect(calls, 1);
    pending.complete(snapshot());
    await t.pump();
    await t.pumpWidget(const SizedBox());
  });
  testWidgets('renders runtime rates and explicit unavailable measurements',
      (t) async {
    await t.pumpWidget(wrap(() async => snapshot()));
    await t.pump();
    expect(find.textContaining('32.9'), findsWidgets);
    expect(find.textContaining('Local model A'), findsWidgets);
    expect(find.textContaining('Not reported'), findsWidgets);
    expect(find.textContaining('925,743'), findsWidgets);
    await t.pumpWidget(const SizedBox());
  });

  testWidgets('invalid rates never become zero or enter a chart', (t) async {
    await t.pumpWidget(wrap(() async => snapshot(rate: double.nan)));
    await t.pump();
    expect(find.textContaining('NaN'), findsNothing);
    expect(find.text('Measured'), findsNothing);
    expect(find.textContaining('Not reported'), findsWidgets);
    await t.pumpWidget(const SizedBox());
  });

  testWidgets('explains a reset and does not announce a zero peak without data',
      (t) async {
    final semantics = t.ensureSemantics();
    final data = snapshot(rate: null);
    final first = (data['models'] as List).first as Map;
    first['status'] = 'warming_up';
    first['reason'] = 'Runtime counters reset';
    first['counter_scope'] = 'current_request';
    await t.pumpWidget(wrap(() async => data));
    await t.pump();
    expect(find.textContaining('Runtime counters reset'), findsWidgets);
    expect(find.textContaining('Current request'), findsWidgets);
    expect(find.bySemanticsLabel(RegExp('Peak 0.0')), findsNothing);
    expect(find.bySemanticsLabel(RegExp('Peak Not reported')), findsWidgets);
    await t.pumpWidget(const SizedBox());
    semantics.dispose();
  });

  testWidgets('polls serially and pause cancels further observation',
      (t) async {
    var calls = 0;
    final pending = Completer<Map<String, dynamic>>();
    await t.pumpWidget(wrap(() {
      calls++;
      return pending.future;
    }));
    await t.pump(const Duration(seconds: 3));
    expect(calls, 1);
    pending.complete(snapshot());
    await t.pump();
    await t.tap(find.text('Pause'));
    await t.pump(const Duration(seconds: 3));
    expect(calls, 1);
    expect(find.textContaining('Paused'), findsWidgets);
    expect(find.text('Measured'), findsNothing);
    expect(find.text('32.9 tok/s'), findsNothing);
    await t.pumpWidget(const SizedBox());
  });

  testWidgets('failed refresh marks retained data stale', (t) async {
    var calls = 0;
    await t.pumpWidget(wrap(() async {
      if (++calls == 1) return snapshot();
      throw StateError('private transport detail');
    }));
    await t.pump();
    await t.pump(const Duration(seconds: 1));
    await t.pump();
    expect(find.textContaining('Stale'), findsWidgets);
    expect(find.text('Measured'), findsNothing);
    expect(find.text('32.9 tok/s'), findsNothing);
    expect(find.textContaining('private transport detail'), findsNothing);
    await t.pumpWidget(const SizedBox());
  });

  testWidgets('fits a narrow window at increased text scale', (t) async {
    t.view.physicalSize = const Size(390, 844);
    t.view.devicePixelRatio = 1;
    addTearDown(t.view.resetPhysicalSize);
    addTearDown(t.view.resetDevicePixelRatio);
    await t.pumpWidget(wrap(() async => snapshot(), scale: 1.6));
    await t.pump();
    expect(t.takeException(), isNull);
    await t.pumpWidget(const SizedBox());
  });
}
