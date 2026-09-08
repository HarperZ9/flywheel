// First-run cliffs, closed and held closed: Chat must never default to a
// keyless endpoint (a silent empty first send), the picker must not offer
// one, and an empty key roster must state itself instead of hiding the only
// Set-key path.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/fw.dart';
import 'package:flywheel_desktop/widgets/keys_panel.dart';
import 'package:flywheel_desktop/widgets/model_picker.dart';

EndpointRow _row(String name, String credential) => EndpointRow.fromJson(
    {'name': name, 'backend': 'b', 'credential': credential});

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  group('defaultEndpoint', () {
    test('skips keyless rows even when they sit first in the roster', () {
      final rows = [
        _row('keyless-a', 'absent'),
        _row('keyless-b', 'absent'),
        _row('local', 'local-none'),
      ];
      expect(defaultEndpoint(rows)?.name, 'local');
    });

    test('prefers the subscription tier over a keyed provider', () {
      final rows = [
        _row('keyed', 'present'),
        _row('claude-cli', 'cli-auth'),
      ];
      expect(defaultEndpoint(rows)?.name, 'claude-cli');
    });

    test('returns null when nothing on the roster can answer', () {
      expect(defaultEndpoint([_row('a', 'absent'), _row('b', 'absent')]),
          isNull);
      expect(defaultEndpoint([]), isNull);
    });

    test('roster order breaks ties within a tier', () {
      final rows = [_row('first-keyed', 'present'), _row('second', 'present')];
      expect(defaultEndpoint(rows)?.name, 'first-keyed');
    });
  });

  group('model picker gating', () {
    testWidgets('a no-key row does not select; a usable row does',
        (tester) async {
      String? picked;
      await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: OutlinedButton(
                onPressed: () async {
                  picked = await showModelPicker(
                      context,
                      [_row('dead', 'absent'), _row('alive', 'local-none')],
                      null);
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      // Tapping the keyless row leaves the dialog open and selects nothing.
      await tester.tap(find.text('dead'), warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(find.text('Search models…'), findsOneWidget); // still open
      expect(picked, isNull);

      // Tapping the usable row selects and closes.
      await tester.tap(find.text('alive'));
      await tester.pumpAndSettle();
      expect(picked, 'alive');
    });
  });

  group('keys panel first run', () {
    testWidgets('an all-absent roster still renders a Set path per key',
        (tester) async {
      await tester.pumpWidget(_wrap(KeysPanel(
        doc: const {
          'available': true,
          'note': 'presence and source only',
          'entries': [
            {'name': 'ANTHROPIC_API_KEY', 'source': 'absent'},
            {'name': 'GEMINI_API_KEY', 'source': 'absent'},
          ],
        },
        onSet: (n, v) async => {'stored': n},
        onDelete: (n) async => {},
        onChanged: () {},
      )));
      expect(find.text('Set'), findsNWidgets(2)); // the in-GUI path exists
      expect(find.text('ABSENT'), findsNWidgets(2)); // honesty stays visible
    });

    testWidgets('an empty roster states itself instead of rendering blank',
        (tester) async {
      await tester.pumpWidget(_wrap(KeysPanel(
        doc: const {'available': true, 'note': '', 'entries': []},
        onSet: (n, v) async => {},
        onDelete: (n) async => {},
        onChanged: () {},
      )));
      expect(find.byType(HonestNull), findsOneWidget);
      expect(find.textContaining('no provider key names'), findsOneWidget);
    });

    testWidgets('native Bulletin identity never renders generic Set',
        (tester) async {
      var genericSetCalls = 0;
      var createCalls = 0;
      await tester.pumpWidget(_wrap(KeysPanel(
        doc: const {
          'available': true,
          'entries': [
            {
              'name': 'BULLETIN_AGENT_JWK',
              'source': 'absent',
              'kind': 'native_identity',
              'protected': true,
              'generic_set_allowed': false,
              'set_action': 'bulletin_identity',
            },
            {'name': 'OPENAI_API_KEY', 'source': 'absent'},
          ],
        },
        onSet: (n, v) async {
          genericSetCalls++;
          return {'stored': n};
        },
        onDelete: (n) async => {},
        onCreateBulletinIdentity: () async {
          createCalls++;
          return {'ok': true, 'action': 'created_stored'};
        },
        onRegisterBulletinIdentity: () async => {},
        onChanged: () {},
      )));

      expect(find.text('Set'), findsOneWidget);
      expect(find.text('Create identity'), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
      await tester.tap(find.text('Create identity'));
      await tester.pumpAndSettle();
      expect(createCalls, 1);
      expect(genericSetCalls, 0);
      expect(find.textContaining('created_stored'), findsOneWidget);
    });

    testWidgets('keychain Bulletin identity renders register and remove',
        (tester) async {
      var registerCalls = 0;
      var removed = '';
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
        onDelete: (n) async {
          removed = n;
          return {'deleted': n};
        },
        onCreateBulletinIdentity: () async => {},
        onRegisterBulletinIdentity: () async {
          registerCalls++;
          return {'ok': true, 'action': 'registered'};
        },
        onChanged: () {},
      )));

      expect(find.text('Set'), findsNothing);
      expect(find.text('Register'), findsOneWidget);
      expect(find.text('Remove'), findsOneWidget);
      await tester.tap(find.text('Register'));
      await tester.pumpAndSettle();
      expect(registerCalls, 1);
      expect(find.textContaining('registered'), findsOneWidget);
      await tester.tap(find.text('Remove'));
      await tester.pumpAndSettle();
      expect(removed, 'BULLETIN_AGENT_JWK');
    });

    testWidgets(
        'native Bulletin identity disables create when signing is missing',
        (tester) async {
      var createCalls = 0;
      await tester.pumpWidget(_wrap(KeysPanel(
        doc: const {
          'available': true,
          'entries': [
            {
              'name': 'BULLETIN_AGENT_JWK',
              'source': 'absent',
              'generic_set_allowed': false,
              'set_action': 'bulletin_identity',
            },
          ],
        },
        bulletinIdentity: const {
          'source': 'absent',
          'keychain_available': true,
          'signing_available': false,
          'create_available': false,
          'unavailable_reason': 'SIGNING_UNAVAILABLE',
        },
        onSet: (n, v) async => {'stored': n},
        onDelete: (n) async => {},
        onCreateBulletinIdentity: () async {
          createCalls++;
          return {'ok': true};
        },
        onRegisterBulletinIdentity: () async => {},
        onChanged: () {},
      )));

      expect(find.textContaining('signing support is unavailable'),
          findsOneWidget);
      await tester.tap(find.text('Create identity'), warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(createCalls, 0);
    });

    testWidgets(
        'native Bulletin identity disables register when signing is missing',
        (tester) async {
      var registerCalls = 0;
      await tester.pumpWidget(_wrap(KeysPanel(
        doc: const {
          'available': true,
          'entries': [
            {
              'name': 'BULLETIN_AGENT_JWK',
              'source': 'keychain',
              'generic_set_allowed': false,
              'set_action': 'bulletin_identity',
            },
          ],
        },
        bulletinIdentity: const {
          'source': 'keychain',
          'keychain_available': true,
          'signing_available': false,
          'register_available': false,
          'unavailable_reason': 'SIGNING_UNAVAILABLE',
        },
        onSet: (n, v) async => {'stored': n},
        onDelete: (n) async => {},
        onCreateBulletinIdentity: () async => {},
        onRegisterBulletinIdentity: () async {
          registerCalls++;
          return {'ok': true};
        },
        onChanged: () {},
      )));

      expect(find.textContaining('signing support is unavailable'),
          findsOneWidget);
      await tester.tap(find.text('Register'), warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(registerCalls, 0);
    });
  });
}
