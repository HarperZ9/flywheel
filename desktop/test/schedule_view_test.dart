// The Schedule destination: what runs unattended, what it owes, and the
// half a scheduler usually hides. A tick that fires one schedule and
// refuses another has to print both, so the refusal is asserted here
// beside the fired count.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_schedule.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/schedule_view.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _rosterBody = {
  'schema': 'flywheel.schedule-roster/v1',
  'read_at': '2026-09-06T09:00:00Z',
  'count': 2,
  'any_chain_broken': true,
  'schedules': [
    {
      'schedule': {
        'schedule_id': 'sched_hourly_bench',
        'event': 'bench.completed',
        'every_seconds': 3600,
        'starts_at': '2026-09-01T00:00:00Z',
        'catch_up': 'latest',
      },
      'fires': 4,
      'chain_intact': true,
      'last_fired_for': '2026-09-06T08:00:00Z',
      'pending': {'occurrences': [], 'due': 2, 'truncated': false},
      'plan': {
        'policy': 'latest',
        'fire': [],
        'skipped': [],
        'truncated': false,
      },
    },
    {
      'schedule': {
        'schedule_id': 'sched_daily_route',
        'event': 'route.completed',
        'every_seconds': 86400,
        'starts_at': '2026-09-01T00:00:00Z',
        'catch_up': 'drop',
      },
      'fires': 1,
      'chain_intact': false,
      'last_fired_for': '2026-09-05T00:00:00Z',
      'pending': {'occurrences': [], 'due': 0, 'truncated': false},
      'plan': {
        'policy': 'drop',
        'fire': [],
        'skipped': [],
        'truncated': false,
      },
    },
  ],
};

const _tickBody = {
  'schema': 'flywheel.schedule-tick/v1',
  'ticked_at': '2026-09-06T09:00:05Z',
  'evaluated': 2,
  'fired': 1,
  'skipped': 1,
  'results': [
    {'schedule_id': 'sched_hourly_bench', 'fired': 1},
    {
      'schedule_id': 'sched_daily_route',
      'fired': 0,
      'refused': 'the fire chain for this schedule is broken',
    },
  ],
};

ScheduleApi _api(List<String> seen) => ScheduleApi(
      httpClient: MockClient((request) async {
        seen.add('${request.method} ${request.url.path}');
        final body =
            request.url.path == '/api/schedule/tick' ? _tickBody : _rosterBody;
        return http.Response(jsonEncode(body), 200,
            headers: {'content-type': 'application/json'});
      }),
    );

/// A viewport tall enough to build every row, so an assertion that fails
/// means the surface omitted something rather than the list not having
/// scrolled to it.
void _tallViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1400, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

void main() {
  testWidgets('ScheduleView reads the roster and names the owed work',
      (tester) async {
    _tallViewport(tester);
    final seen = <String>[];
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: ScheduleView(api: _api(seen), alive: true))));
    await tester.pumpAndSettle();

    expect(seen, ['GET /api/schedule']);
    expect(find.text('sched_hourly_bench'), findsOneWidget);
    expect(find.text('bench.completed'), findsOneWidget);
    // seconds read as a duration a person plans around
    expect(find.text('every 1h'), findsOneWidget);
    expect(find.text('every 1d'), findsOneWidget);
    expect(find.text('latest'), findsOneWidget);
    // the pill carries the due count for that one schedule
    expect(find.text('2 DUE'), findsOneWidget);
    expect(find.text('0 DUE'), findsOneWidget);
    // a broken fire history is stated, not folded into a green count
    expect(find.text('broken'), findsOneWidget);
    expect(find.textContaining('no longer verifies'), findsOneWidget);
  });

  testWidgets('a tick prints what fired and what it refused', (tester) async {
    _tallViewport(tester);
    final seen = <String>[];
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: ScheduleView(api: _api(seen), alive: true))));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('schedule-tick')));
    await tester.pumpAndSettle();

    // a tick is a pull, and it re-reads the roster afterwards
    expect(seen, [
      'GET /api/schedule',
      'POST /api/schedule/tick',
      'GET /api/schedule',
    ]);
    expect(find.textContaining('2 evaluated, 1 fired, 1 passed over'),
        findsOneWidget);
    // the refusal is the honest half; it sits beside the fired count
    expect(
        find.textContaining('the fire chain for this schedule is broken'),
        findsOneWidget);
  });

  testWidgets('ScheduleView names the command when offline', (tester) async {
    final api = ScheduleApi(httpClient: MockClient((request) async {
      throw StateError('offline surface must not call the engine');
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: ScheduleView(api: api, alive: false))));
    expect(find.textContaining('engine is offline'), findsOneWidget);
    expect(find.text('flywheel up'), findsOneWidget);
  });
}
