// callable_lane_test.dart - what may be called, and what it demands.
//
// /api/lanes/callable answers a different question from the roster: not what
// is installed, but what may be invoked and at what governance tier. The app
// never called it. The shapes here are what the live engine returned.

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/callable_lane.dart';

void main() {
  test('the live shape parses, tier and organ included', () {
    final lanes = CallableLane.listFrom(const {
      'lanes': [
        {
          'name': 'gather',
          'min_tier': 'T1',
          'description': 'research intake + provenance receipts',
          'organ': 'perception',
        },
        {
          'name': 'accountable-surface',
          'min_tier': 'T2',
          'description': 'actuates, so T2',
          'organ': 'actuation',
        },
      ]
    });
    expect(lanes, hasLength(2));
    expect(lanes.first.name, 'gather');
    expect(lanes.first.minTier, 'T1');
    expect(lanes.first.organ, 'perception');
    expect(lanes.last.minTier, 'T2');
  });

  test('a lane the engine did not name is not a lane', () {
    final lanes = CallableLane.listFrom(const {
      'lanes': [
        {'min_tier': 'T1', 'description': 'nameless'},
        {'name': 'forum'},
      ]
    });
    expect(lanes, hasLength(1));
    expect(lanes.single.name, 'forum');
  });

  test('malformed rows are dropped, not faked', () {
    expect(
        CallableLane.listFrom(const {
          'lanes': ['gather', 7, null]
        }),
        isEmpty);
  });

  test('a missing or wrongly typed lanes key yields no lanes', () {
    expect(CallableLane.listFrom(const {}), isEmpty);
    expect(CallableLane.listFrom(const {'lanes': 'gather'}), isEmpty);
  });

  test('absent fields degrade to empty rather than a made-up tier', () {
    final lane = CallableLane.fromJson(const {'name': 'index'});
    expect(lane.name, 'index');
    expect(lane.minTier, '');
    expect(lane.organ, '');
    expect(lane.description, '');
  });
}
