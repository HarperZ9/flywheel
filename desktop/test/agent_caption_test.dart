import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/agent_trace_reader.dart';
import 'package:flywheel_desktop/models/agent_caption.dart';
import 'package:flywheel_desktop/models/agent_trace_record.dart';
import 'package:flywheel_desktop/controllers/agent_caption_controller.dart';
import 'agent_caption_fixtures.dart';

void main() {
  final received = DateTime.utc(2026, 9, 10, 12);
  test('assistant output and tool records never become hidden reasoning', () {
    final pages = captionPages([
      captionLedger('assistant', 'I think this is the answer. naïve ✓'),
      captionLedger('tool_call', 'read {"path":"synthetic.txt"}'),
      captionLedger('tool_result', 'original source\nline two',
          meta: {'tool': 'read', 'ok': true}),
    ]);
    final rows = [
      for (var i = 0; i < pages.length; i++)
        AgentCaption.fromRecord(captionPage(pages[i], i).record, received)!
    ];
    expect(rows.map((r) => r.kind), [
      CaptionKind.assistantOutput,
      CaptionKind.toolActivity,
      CaptionKind.toolActivity
    ]);
    expect(rows[0].text, 'I think this is the answer. naïve ✓');
    expect(rows[1].label, contains('recorded'));
    expect(rows[2].record.sequence, 2);
    expect(rows[2].eventTimestamp, isNull);
    expect(rows[2].receivedAt, received);
    expect(CaptionKind.providerSummary.wire, 'provider_summary');
  });

  test('opaque blocks and untyped reasoning fields cannot manufacture captions',
      () {
    final pages = captionPages([
      {
        'type': 'reasoning',
        'text': 'not a supported channel',
        'signature': 'opaque'
      },
      {'type': 'redacted_thinking', 'data': 'opaque'},
      {'type': 'provider_summary', 'text': 'untyped claim'},
    ], kind: 'progress');
    for (var i = 0; i < pages.length; i++) {
      expect(AgentCaption.fromRecord(captionPage(pages[i], i).record, received),
          isNull);
    }
  });

  test('typed model inference records become inference activity, not reasoning',
      () {
    final pages = captionPages([
      captionLedger('model_inference', '{"raw":"not shown as caption"}', meta: {
        'schema': 'flywheel.gateway-agent-inference/v1',
        'ordinal': 1,
        'binding_sha256': 'a' * 64,
        'endpoint': 'ollama',
        'model_id': 'qwen2.5-coder:14b',
        'phase': 'response_received',
        'observed_at_utc': '2026-09-10T12:00:00Z',
        'elapsed_ms': 125,
        'reason': null,
      }),
      captionLedger('model_inference', 'bad', meta: {
        'schema': 'flywheel.gateway-agent-inference/v1',
        'ordinal': 2,
        'binding_sha256': 'a' * 64,
        'endpoint': 'ollama',
        'model_id': 'qwen2.5-coder:14b',
        'phase': 'reasoning',
        'observed_at_utc': '2026-09-10T12:00:00Z',
        'elapsed_ms': 125,
        'reason': null,
      }),
    ]);

    final caption =
        AgentCaption.fromRecord(captionPage(pages[0], 0).record, received)!;
    expect(caption.kind, CaptionKind.inferenceActivity);
    expect(caption.label, 'Inference response received');
    expect(caption.text, contains('endpoint ollama'));
    expect(caption.text, contains('model qwen2.5-coder:14b'));
    expect(caption.text, isNot(contains('raw')));
    expect(caption.text.toLowerCase(), isNot(contains('reasoning')));
    expect(AgentCaption.fromRecord(captionPage(pages[1], 1).record, received),
        isNull);
  });

  test('only typed reported progress maps; mirrored output is omitted', () {
    final pages = captionPages([
      {'type': 'budget', 'step': 2, 'max_steps': 4, 'remaining': 2},
      {'type': 'budget', 'step': 5, 'max_steps': 4, 'remaining': -1},
      {'type': 'assistant', 'text': 'short mirror'},
      {'type': 'tool_result', 'output': 'short mirror', 'ok': true},
    ], kind: 'progress');
    final caption =
        AgentCaption.fromRecord(captionPage(pages[0], 0).record, received)!;
    expect(caption.kind, CaptionKind.progress);
    expect(caption.text, 'Step 2 of 4 · 2 remaining');
    for (var i = 1; i < pages.length; i++) {
      expect(AgentCaption.fromRecord(captionPage(pages[i], i).record, received),
          isNull);
    }
  });

  test(
      'projection advances read new records, paused follow does not stop reads',
      () async {
    final pages = captionPages(
        [captionLedger('assistant', 'one'), captionLedger('assistant', 'two')]);
    final calls = <int>[];
    final reader = CaptionReader((p, sequence, cancelled) async {
      calls.add(sequence);
      return captionPage(pages[sequence], sequence);
    });
    final controller = AgentCaptionController(
        reader: reader,
        projection: captionProjection(pages, count: 1),
        clock: () => received);
    expect(calls, isEmpty);
    await controller.start();
    controller.setFollowing(false);
    await controller
        .updateProjection(captionProjection(pages, state: 'completed'));
    expect(calls, [0, 1]);
    expect(controller.captions.map((row) => row.text), ['one', 'two']);
    expect(controller.following, isFalse);
    expect(controller.caughtUp, isTrue);
    expect(controller.providerSummaryAvailable, isFalse);
    controller.close();
    expect(controller.captions, isEmpty);
    controller.dispose();
  });

  test('retry reads same sequence; close cancels and rejects late private text',
      () async {
    final pages =
        captionPages([captionLedger('assistant', 'private synthetic')]);
    var calls = 0;
    final pending = Completer<TracePage>();
    final aborted = Completer<void>();
    final controller = AgentCaptionController(
        projection: captionProjection(pages),
        reader: CaptionReader((p, sequence, cancelled) {
          calls++;
          expect(sequence, 0);
          cancelled!.then((_) {
            if (!aborted.isCompleted) aborted.complete();
          });
          if (calls == 1) {
            return Future.error(
                const TraceReadException(TraceReadFailure.transport));
          }
          return pending.future;
        }));
    await controller.start();
    expect(controller.failure, TraceReadFailure.transport);
    final retry = controller.retry();
    controller.close();
    await aborted.future;
    pending.complete(captionPage(pages.single, 0));
    await retry;
    expect(calls, 2);
    expect(controller.captions, isEmpty);
    expect(controller.active, isFalse);
    controller.dispose();
  });
}
