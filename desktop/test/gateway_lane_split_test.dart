// The lane model and the lane client calls live in their own files so the
// two gateway files stay under the 300-line gate. These tests pin that split:
// the new files carry the lane code, the old imports still resolve to the same
// types, and the roster call keeps its request and its parse contract.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/gateway_models.dart' as gateway_models;
import 'package:flywheel_desktop/models/lane_models.dart';

const _gatedFiles = [
  'lib/models/gateway_models.dart',
  'lib/models/lane_models.dart',
  'lib/client/gateway_client.dart',
  'lib/client/gateway_lane_client.dart',
];

void main() {
  test('each file in the split stays under 300 lines', () {
    for (final path in _gatedFiles) {
      final lines = File(path).readAsLinesSync().length;
      expect(lines, lessThanOrEqualTo(300), reason: '$path has $lines lines');
    }
  });

  test('gateway_models.dart re-exports the lane types unchanged', () {
    final lane = gateway_models.Lane.fromJson(const {'name': 'gather'});
    expect(lane, isA<Lane>());
    final roster = gateway_models.LaneRoster.fromJson(const {'lanes': []});
    expect(roster, isA<LaneRoster>());
  });

  test('Lane.fromJson keeps its defaults and field mapping', () {
    final bare = Lane.fromJson(const {});
    expect(bare.status, 'missing');
    expect(bare.tools, isNull);
    expect(bare.packageInstallable, isTrue);
    expect(bare.isInstallable, isFalse);

    final full = Lane.fromJson(const {
      'name': 'learn',
      'kind': 'npm',
      'installed_version': '0.3.0',
      'expected_version': '0.3.0',
      'status': 'live',
      'organ': 'tutor',
      'role': 'study',
      'detail': 'ok',
      'tools': 12,
      'package_installable': true,
    });
    expect(full.isLive, isTrue);
    expect(full.installedVersion, '0.3.0');
    expect(full.tools, 12);
    expect(full.isInstallable, isTrue);
    expect(
        Lane.fromJson(const {'kind': 'pip', 'package_installable': false})
            .isInstallable,
        isFalse);
  });

  test('the lane client extension sends the roster request', () async {
    final paths = <String>[];
    final client = GatewayClient(httpClient: MockClient((r) async {
      paths.add(r.url.toString());
      return http.Response(
          jsonEncode({
            'n_lanes': 1,
            'by_status': {'declared': 1},
            'all_live': false,
            'lanes': [
              {'name': 'crucible', 'kind': 'bundled', 'status': 'declared'}
            ],
          }),
          200);
    }));
    final plain = await GatewayLaneClient(client).laneRoster();
    final probed = await client.laneRoster(probe: true);
    expect(paths, [
      '${GatewayClient.loopback}/api/lanes',
      '${GatewayClient.loopback}/api/lanes?probe=true',
    ]);
    expect(plain.nLanes, 1);
    expect(plain.byStatus, {'declared': 1});
    expect(probed.lanes.single.name, 'crucible');
    expect(probed.lanes.single.isDeclared, isTrue);
  });

  test('a roster without its inventory fields is still refused', () async {
    final client = GatewayClient(
        httpClient: MockClient((_) async => http.Response('{}', 200)));
    await expectLater(client.laneRoster(), throwsFormatException);
  });
}
