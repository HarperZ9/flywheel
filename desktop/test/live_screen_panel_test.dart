import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/live_screen_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/live_screen_panel.dart';

void main() {
  final source = LiveScreenSource.fromJson(const {
    'source_id': 'display:primary',
    'kind': 'display',
    'label': 'Primary display',
    'backend': 'gdi',
    'available': true,
  });
  Widget host(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)));

  testWidgets('opening the panel never starts capture', (tester) async {
    var starts = 0;
    await tester.pumpWidget(host(LiveScreenPanel(
      sources: [source],
      selected: const {'display:primary'},
      state: ScreenCaptureState.stopped,
      onSelectionChanged: (_) {},
      onStart: () => starts++,
    )));
    expect(starts, 0);
    expect(find.text('Not sharing'), findsOneWidget);
    expect(find.text('No model delivery recorded'), findsOneWidget);
    await tester.tap(find.text('Start sharing'));
    expect(starts, 1);
  });

  testWidgets('disconnect preserves stop control for an existing session',
      (tester) async {
    var stops = 0;
    await tester.pumpWidget(host(LiveScreenPanel(
      sources: [source],
      selected: const {'display:primary'},
      state: ScreenCaptureState.disconnected,
      hasSession: true,
      onSelectionChanged: (_) {},
      onStop: () => stops++,
    )));
    expect(find.text('Disconnected'), findsOneWidget);
    expect(find.text('Start sharing'), findsNothing);
    await tester.tap(find.text('Stop sharing'));
    expect(stops, 1);
  });

  testWidgets('capture running is not labelled model vision', (tester) async {
    await tester.pumpWidget(host(LiveScreenPanel(
      sources: [source],
      selected: const {'display:primary'},
      state: ScreenCaptureState.running,
      onSelectionChanged: (_) {},
      onPause: () {},
      onStop: () {},
    )));
    expect(find.text('Sharing selected sources'), findsOneWidget);
    expect(find.text('No model delivery recorded'), findsOneWidget);
    expect(find.text('Live preview unavailable'), findsOneWidget);
    expect(find.text('Pause'), findsOneWidget);
    expect(find.text('Stop sharing'), findsOneWidget);
  });

  testWidgets('preview monitor changes without changing shared sources',
      (tester) async {
    String? viewed;
    var selectionChanges = 0;
    final second = LiveScreenSource.fromJson(const {
      'source_id': 'display:second',
      'kind': 'display',
      'label': 'Second display',
      'backend': 'gdi',
      'available': true,
    });
    await tester.pumpWidget(host(LiveScreenPanel(
      sources: [source, second],
      selected: const {'display:primary', 'display:second'},
      state: ScreenCaptureState.running,
      previewSourceId: 'display:primary',
      onPreviewSourceChanged: (id) => viewed = id,
      onSelectionChanged: (_) => selectionChanges++,
    )));
    await tester
        .tap(find.byKey(const ValueKey('screen-preview-display:second')));
    expect(viewed, 'display:second');
    expect(selectionChanges, 0);
  });

  testWidgets('disconnected session does not present cached delivery as live',
      (tester) async {
    final frame = LiveScreenFrame.fromJson({
      'session_id': 's',
      'source_id': 'display:primary',
      'source_sequence': 1,
      'aggregate_sequence': 1,
      'frame_sha256': 'a' * 64,
      'width': 100,
      'height': 100,
      'captured_at_utc': '2026-09-15T10:00:00Z',
    });
    final delivery = LiveScreenDelivery.fromJson({
      'session_id': 's',
      'source_id': 'display:primary',
      'source_sequence': 1,
      'frame_sha256': 'a' * 64,
      'model_route': 'selected-route',
      'model': 'vision-model',
      'aggregate_sequence': 1,
      'frame': {
        'session_id': 's',
        'source_id': 'display:primary',
        'source_sequence': 1,
        'aggregate_sequence': 1,
        'frame_sha256': 'a' * 64,
      },
      'delivery_mode': 'sampled_image',
      'delivered_at_utc': '2026-09-15T10:00:00Z',
      'frame_age_ms': 0,
      'stale': false,
    });
    await tester.pumpWidget(host(LiveScreenPanel(
      sources: [source],
      selected: const {'display:primary'},
      state: ScreenCaptureState.disconnected,
      onSelectionChanged: (_) {},
      delivery: delivery,
      deliveredFrame: frame,
    )));
    expect(find.text('Disconnected'), findsOneWidget);
    expect(find.textContaining('Historical delivery'), findsOneWidget);
    expect(find.text('Sharing selected sources'), findsNothing);
  });
}
