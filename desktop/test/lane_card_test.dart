// lane_card_test.dart - the roster card, and the button it must not offer.
//
// The gateway answers `install_lane` for a bundled or an http lane with "no
// install needed". A card that offers Install for one of those runs the call,
// succeeds, changes nothing, and tells the operator the lane was installed.
// bulletin is the live case: it runs on the open web, so its installed_version
// is null forever and the old `installedVersion == null` guard let it through.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/lanes_view.dart';

Lane _lane(String name, String kind, {String? installed}) => Lane.fromJson({
      'name': name,
      'kind': kind,
      'installed_version': installed,
      'expected_version': '0.2.0',
      'status': 'live',
      'organ': 'correspondence',
      'role': 'the open board',
      'detail': 'reachable at its endpoint',
    });

Future<void> _pump(WidgetTester tester, Lane lane) => tester.pumpWidget(
      MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
          body: LaneCard(
            lane: lane,
            onInstall: (_) async => const {'installed': true},
          ),
        ),
      ),
    );

void main() {
  testWidgets('a pip lane with nothing installed offers the install',
      (tester) async {
    await _pump(tester, _lane('mneme', 'pip'));
    expect(find.text('Install'), findsOneWidget);
  });

  testWidgets('a remote lane never offers an install it cannot run',
      (tester) async {
    await _pump(tester, _lane('bulletin', 'http'));
    expect(find.text('Install'), findsNothing);
  });

  testWidgets('a bundled lane carries no install either', (tester) async {
    // A bundled lane reports the engine's own version, so it is covered twice
    // over. The kind is the load-bearing half: the version could go null on a
    // read that fails and the button must still stay away.
    await _pump(tester, _lane('flywheel', 'bundled'));
    expect(find.text('Install'), findsNothing);
  });

  testWidgets('an installed pip lane has nothing left to install',
      (tester) async {
    await _pump(tester, _lane('mneme', 'pip', installed: '0.2.0'));
    expect(find.text('Install'), findsNothing);
  });

  testWidgets('a lane added to the engine renders in its own words',
      (tester) async {
    // The card falls back to the raw lane name, so a missing identity entry
    // looks like a working card rather than like the gap it is.
    await _pump(tester, _lane('bulletin', 'http'));
    expect(find.text('Bulletin'), findsOneWidget);
    expect(find.textContaining('accounts belong to agents'), findsOneWidget);
  });
}
