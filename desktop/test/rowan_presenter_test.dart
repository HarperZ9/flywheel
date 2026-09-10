import 'dart:async';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/rowan_avatar.dart';
import 'package:flywheel_desktop/widgets/rowan_presenter.dart';
import 'package:flywheel_desktop/widgets/rowan_shader.dart';

void main() {
  testWidgets(
      'presenter starts static, turns with keyboard, and opts into motion',
      (tester) async {
    final semantics = tester.ensureSemantics();
    final program = await tester.runAsync(RowanShader.load);
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: SingleChildScrollView(
                child: RowanPresenter(loadProgram: () async => program!)))));
    await tester.pumpAndSettle();
    expect(tester.widget<RowanAvatar>(find.byType(RowanAvatar)).size, 320);
    expect(
        tester.widget<RowanAvatar>(find.byType(RowanAvatar)).animated, isFalse);
    expect(tester.widget<Slider>(find.byType(Slider)).onChanged, isNotNull);
    expect(find.bySemanticsLabel('Turn Rowan'), findsOneWidget);
    tester.widget<Slider>(find.byType(Slider)).focusNode!.requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    expect(tester.widget<Slider>(find.byType(Slider)).value, greaterThan(0));
    expect(tester.widget<RowanAvatar>(find.byType(RowanAvatar)).pose.yaw,
        tester.widget<Slider>(find.byType(Slider)).value);
    await tester.ensureVisible(find.text('Motion'));
    await tester.tap(find.text('Motion'));
    await tester.pump();
    expect(
        tester.widget<RowanAvatar>(find.byType(RowanAvatar)).animated, isTrue);
    await tester.tap(find.text('Motion'));
    await tester.pumpAndSettle();
    expect(
        tester.widget<RowanAvatar>(find.byType(RowanAvatar)).animated, isFalse);
    expect(tester.takeException(), isNull);
    semantics.dispose();
  });

  testWidgets(
      'pending renderer explains disabled controls and drawn placeholder',
      (tester) async {
    final semantics = tester.ensureSemantics();
    final pending = Completer<ui.FragmentProgram>();
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home:
            Scaffold(body: RowanPresenter(loadProgram: () => pending.future))));
    await tester.pump();
    expect(
        find.textContaining('Loading the modeled renderer.'), findsOneWidget);
    expect(find.bySemanticsLabel('Rowan, loading modeled renderer'),
        findsOneWidget);
    expect(tester.widget<Slider>(find.byType(Slider)).onChanged, isNull);
    expect(tester.widget<SwitchListTile>(find.byType(SwitchListTile)).onChanged,
        isNull);
    pending.completeError(UnsupportedError('private driver detail'));
    await tester.pumpAndSettle();
    expect(
        find.textContaining('Modeled renderer unavailable.'), findsOneWidget);
    expect(find.textContaining('private driver detail'), findsNothing);
    expect(tester.takeException(), isNull);
    semantics.dispose();
  });

  testWidgets('presenter controls fit a narrow viewport', (tester) async {
    tester.view.physicalSize = const Size(320, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final program = await tester.runAsync(RowanShader.load);
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: SingleChildScrollView(
                child: RowanPresenter(loadProgram: () async => program!)))));
    await tester.pumpAndSettle();
    expect(tester.widget<RowanAvatar>(find.byType(RowanAvatar)).size,
        lessThanOrEqualTo(320));
    expect(find.text('Turn'), findsOneWidget);
    expect(find.text('Motion'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
