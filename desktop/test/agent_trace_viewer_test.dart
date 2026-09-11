import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/agent_trace_reader.dart';
import 'package:flywheel_desktop/models/agent_trace_record.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/agent_trace_viewer.dart';
import 'package:flywheel_desktop/widgets/agent_trace_record_view.dart';
import 'agent_trace_chain_test.dart' show chain, chainPage, chainProjection;
import 'agent_trace_models_test.dart' show fixture, operation, journey;
import 'agent_trace_reader_test.dart' show FakeTraceReader, projection;

void main() {
  testWidgets('large original text windows preserve every Unicode character',
      (tester) async {
    final pages = chain(textLength: 33000);
    final record = chainPage(pages.first, chainProjection(pages), 0).record;
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: SingleChildScrollView(
                child: AgentTraceRecordView(record: record)))));
    final windows = <String>[];
    for (var count = 0; count < 3; count++) {
      windows.add(tester
          .widget<SelectableText>(find.byType(SelectableText).last)
          .data!);
      if (count < 2) {
        await tester.ensureVisible(find.text('Next text'));
        await tester.tap(find.text('Next text'));
        await tester.pumpAndSettle();
      }
    }
    expect(windows.join(), record.canonicalText);
    expect(tester.takeException(), isNull);
  });
  testWidgets(
      'private originals require explicit read; unavailable retry only reads',
      (tester) async {
    var reads = 0;
    final pending = Completer<TracePage>();
    final reader = FakeTraceReader((p, sequence) {
      reads++;
      if (reads == 1) {
        return Future.error(
            const TraceReadException(TraceReadFailure.unavailable));
      }
      return pending.future;
    });
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: SingleChildScrollView(
                child: AgentTraceViewer(
                    projection: projection(), reader: reader)))));
    expect(reads, 0);
    expect(find.textContaining('Omitted'), findsOneWidget);
    await tester.tap(find.text('Read private trace'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Unavailable'), findsOneWidget);
    await tester.tap(find.text('Retry read'));
    await tester.pump();
    expect(find.text('Reading private record…'), findsOneWidget);
    pending.complete(TracePage.fromJson(fixture('detail'),
        operationRef: operation,
        journeyRef: journey,
        traceRef: projection().traceRef,
        sequence: 0));
    await tester.pumpAndSettle();
    expect(reads, 2);
    expect(find.textContaining('naïve ✓'), findsOneWidget);
    expect(find.textContaining('Hashes match'), findsOneWidget);
    expect(find.textContaining('semantic truth'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
