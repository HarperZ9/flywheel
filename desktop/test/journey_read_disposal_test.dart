import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'journey_controller_test.dart';

void main() {
  test('disposed initial resume cannot start its subsequent list read', () async {
    final api = ScriptedJourneyApi();
    final h = ControllerHarness(api);
    addTearDown(h.dispose);
    h.sessions.save(JourneySession(journeyRef: journeyA, lens: JourneyLens.verify));
    final pending = Completer<JourneyProjection>();
    api.reply(resumeA, pending.future);
    final read = h.controller.retryRead();
    await api.waitFor(resumeA);
    h.controller.dispose();
    pending.complete(projection());
    await read;
    expect(api.calls, [resumeA]);
  });

  test('initial read finishing after disposal cannot notify or send again', () async {
    final api = ScriptedJourneyApi();
    final h = ControllerHarness(api);
    addTearDown(h.dispose);
    final pending = Completer<List<JourneySummary>>();
    api.reply('list', pending.future);
    final read = h.controller.retryRead();
    await api.waitFor('list');
    h.controller.dispose();
    pending.complete([]);
    await read;
    await h.controller.retryRead();
    expect(api.calls, ['list']);
  });

  test('active projection refresh after disposal ignores its result', () async {
    final api = ScriptedJourneyApi();
    final h = await readyHarness(api);
    final pending = Completer<JourneyProjection>();
    api.reply(resumeA, pending.future);
    final read = h.controller.retryRead();
    await api.waitFor(resumeA);
    h.controller.dispose();
    pending.complete(projection(head: headB));
    await read;
    expect(h.controller.state.projection?.eventHeadSha256, headA);
    expect(api.calls, [resumeA]);
  });
}
