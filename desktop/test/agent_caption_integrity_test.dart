import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/agent_trace_reader.dart';
import 'package:flywheel_desktop/controllers/agent_caption_controller.dart';
import 'agent_caption_fixtures.dart';

void main() {
  test('self-consistent replacement records cannot match the accepted head',
      () async {
    final accepted = captionPages([captionLedger('assistant', 'accepted')]);
    final replaced = captionPages([captionLedger('assistant', 'replacement')]);
    final controller = AgentCaptionController(
        projection: captionProjection(accepted),
        reader:
            CaptionReader((p, s, c) async => captionPage(replaced.single, s)));
    await controller.start();
    expect(controller.failure, TraceReadFailure.integrity);
    expect(controller.captions, isEmpty);
    expect(controller.readCount, 0);
    controller.dispose();
  });

  test('regressing metadata clears the prefix and cannot reopen old binding',
      () async {
    final pages = captionPages(
        [captionLedger('assistant', 'one'), captionLedger('assistant', 'two')]);
    var calls = 0;
    final controller = AgentCaptionController(
        projection: captionProjection(pages),
        reader: CaptionReader((p, s, c) async {
          calls++;
          return captionPage(pages[s], s);
        }));
    await controller.start();
    expect(controller.captions.length, 2);
    await controller.updateProjection(captionProjection(pages, count: 1));
    expect(controller.failure, TraceReadFailure.integrity);
    expect(controller.captions, isEmpty);
    await controller.start();
    await controller.retry();
    expect(calls, 2);
    expect(controller.active, isFalse);
    controller.dispose();
  });

  test('a mismatching next chain record never joins the accepted prefix',
      () async {
    final pages = captionPages(
        [captionLedger('assistant', 'one'), captionLedger('assistant', 'two')]);
    final other = captionPages([
      captionLedger('assistant', 'other'),
      captionLedger('assistant', 'bad')
    ]);
    final controller = AgentCaptionController(
        projection: captionProjection(pages),
        reader: CaptionReader(
            (p, s, c) async => captionPage(s == 0 ? pages[0] : other[1], s)));
    await controller.start();
    expect(controller.failure, TraceReadFailure.integrity);
    expect(controller.captions.map((c) => c.text), ['one']);
    expect(controller.caughtUp, isFalse);
    controller.dispose();
  });
}
