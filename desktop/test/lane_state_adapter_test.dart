// An adapter lane (raw) has no MCP server for the app to start. The engine
// reports it as cannot_launch with code lane_adapter_only, and the Tools view
// must count it with the lanes not in this build, not as a launch defect.

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/lane_models.dart';
import 'package:flywheel_desktop/models/lane_state.dart';

Lane _lane(String name, String state, String code) => Lane.fromJson({
      'name': name,
      'kind': 'bundled',
      'expected_version': '0.4.0',
      'status': 'missing',
      'state': state,
      'code': code,
    });

void main() {
  test('an adapter lane counts as not in build, not as a defect', () {
    final raw = _lane('raw', 'cannot_launch', 'lane_adapter_only');
    expect(isLaneHeld(raw), isTrue);
    expect(laneCountKey(raw), 'not_in_build');
    expect(laneStateLabel(raw), 'not in build');
  });

  test('any other launch code is still a defect', () {
    final broken = _lane('gather', 'cannot_launch', 'frozen_lane_not_in_build');
    expect(isLaneHeld(broken), isFalse);
    expect(laneCountKey(broken), 'cannot_launch');
    expect(laneCountVerdict(laneCountKey(broken)), 'drift');
  });
}
