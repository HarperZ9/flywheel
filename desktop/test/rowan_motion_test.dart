import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/rowan_avatar.dart';
import 'package:flywheel_desktop/widgets/rowan_shader.dart';

RowanShaderPainter painter(WidgetTester tester) => tester
    .widgetList<CustomPaint>(find.byType(CustomPaint))
    .map((widget) => widget.painter)
    .whereType<RowanShaderPainter>()
    .single;

void main() {
  testWidgets('static avatar schedules no continuous motion', (tester) async {
    final program = await tester.runAsync(RowanShader.load);
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: RowanAvatar(loadProgram: () async => program!))));
    await tester.pumpAndSettle();
    expect(painter(tester).motion, isFalse);
    expect(painter(tester).time.value, 0);
    await tester.pump(const Duration(seconds: 1));
    expect(painter(tester).time.value, 0);
    expect(tester.binding.hasScheduledFrame, isFalse);
  });

  testWidgets(
      'opt-in motion pauses for reduced motion, TickerMode and app state',
      (tester) async {
    final program = await tester.runAsync(RowanShader.load);
    Future<ui.FragmentProgram> load() async => program!;
    Widget app({bool reduced = false, bool ticker = true}) => MaterialApp(
        theme: flywheelLightTheme(),
        home: MediaQuery(
            data: MediaQueryData(
                disableAnimations: reduced, size: const Size(800, 600)),
            child: TickerMode(
                enabled: ticker,
                child: Scaffold(
                    body: RowanAvatar(animated: true, loadProgram: load)))));
    await tester.pumpWidget(app());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 20));
    await tester.pump(const Duration(milliseconds: 20));
    expect(painter(tester).motion, isTrue);
    expect(painter(tester).time.value, greaterThan(0));
    for (final widget in [app(reduced: true), app(ticker: false)]) {
      await tester.pumpWidget(widget);
      await tester.pump();
      final stopped = painter(tester).time.value;
      await tester.pump(const Duration(seconds: 1));
      expect(painter(tester).motion, isFalse);
      expect(painter(tester).time.value, stopped);
    }
    await tester.pumpWidget(app());
    await tester.pump();
    expect(painter(tester).motion, isTrue);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    await tester.pump();
    final stopped = painter(tester).time.value;
    await tester.pump(const Duration(seconds: 1));
    expect(painter(tester).motion, isFalse);
    expect(painter(tester).time.value, stopped);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    await tester.pump();
    expect(painter(tester).motion, isTrue);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.binding.hasScheduledFrame, isFalse);
  });

  testWidgets('scrolling offscreen stops motion and returning resumes it',
      (tester) async {
    final program = await tester.runAsync(RowanShader.load);
    final scroll = ScrollController();
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: Padding(
                padding: const EdgeInsets.only(top: 200),
                child: SizedBox(
                    height: 240,
                    child: SingleChildScrollView(
                        controller: scroll,
                        child: Column(children: [
                          RepaintBoundary(
                              child: RowanAvatar(
                                  animated: true,
                                  size: 64,
                                  loadProgram: () async => program!)),
                          const SizedBox(height: 2000),
                        ])))))));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 20));
    await tester.pump(const Duration(milliseconds: 20));
    expect(painter(tester).motion, isTrue);
    scroll.jumpTo(120);
    await tester.pump();
    await tester.pump();
    expect(tester.getTopLeft(find.byType(RowanAvatar)).dy, greaterThan(0),
        reason:
            'the avatar is on-screen but clipped outside its inner viewport');
    final stopped = painter(tester).time.value;
    await tester.pump(const Duration(seconds: 1));
    expect(painter(tester).motion, isFalse);
    expect(painter(tester).time.value, stopped);
    scroll.jumpTo(0);
    await tester.pump();
    await tester.pump();
    expect(painter(tester).motion, isTrue);
    await tester.pump(const Duration(milliseconds: 20));
    await tester.pump(const Duration(milliseconds: 20));
    expect(painter(tester).time.value, greaterThan(stopped));
    await tester.pumpWidget(const SizedBox());
    scroll.dispose();
  });
}
