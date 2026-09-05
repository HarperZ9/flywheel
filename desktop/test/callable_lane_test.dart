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
    expect(lane.unlistedToolTier, '');
  });

  // A lane whose tools do not share one tier. Printing the floor alone tells
  // an operator the whole lane is open at T1 when the tools that publish are
  // not, which is a card that looks finished and is wrong.
  test('a lane that charges two tiers prints both', () {
    final lane = CallableLane.fromJson(const {
      'name': 'bulletin',
      'min_tier': 'T1',
      'unlisted_tool_tier': 'T2',
      'description': 'the open board',
      'organ': 'correspondence',
    });
    expect(lane.minTier, 'T1');
    expect(lane.unlistedToolTier, 'T2');
    expect(lane.tierLabel, 'T1/T2');
  });

  test('a lane with one tier prints it once', () {
    expect(
        CallableLane.fromJson(const {'name': 'gather', 'min_tier': 'T1'})
            .tierLabel,
        'T1');
    // An engine that named the same tier twice is not a split.
    expect(
        CallableLane.fromJson(const {
          'name': 'gather',
          'min_tier': 'T1',
          'unlisted_tool_tier': 'T1',
        }).tierLabel,
        'T1');
  });
}
