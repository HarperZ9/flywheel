import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/keys_panel.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets('delayed Bulletin remove does not update after disposal',
      (tester) async {
    final deleteResult = Completer<Map<String, dynamic>>();
    var changed = 0;

    await tester.pumpWidget(_wrap(KeysPanel(
      doc: const {
        'available': true,
        'entries': [
          {
            'name': 'BULLETIN_AGENT_JWK',
            'source': 'keychain',
            'kind': 'native_identity',
            'generic_set_allowed': false,
            'set_action': 'bulletin_identity',
          },
        ],
      },
      onSet: (n, v) async => {'stored': n},
      onDelete: (n) => deleteResult.future,
      onCreateBulletinIdentity: () async => {},
      onRegisterBulletinIdentity: () async => {},
      onChanged: () => changed++,
    )));

    await tester.tap(find.text('Remove'));
    await tester.pumpWidget(const SizedBox.shrink());
    deleteResult.complete({'deleted': 'BULLETIN_AGENT_JWK'});
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(changed, 0);
  });
}
