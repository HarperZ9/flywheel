// remote_surface_test.dart - the remote half of the relay card.
//
// The shapes here are what the live gateway returned from
// GET /api/relay/remote against a running relay lane.
//
// Two things are load-bearing. First, that "unreported" and "off" stay
// different facts: rendering an unreachable lane as a configured-off surface
// tells an operator their working setup is off. Second, that a value can
// never reach the view through this model even if relay regressed and sent
// one, because presence is the whole contract.

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/remote_surface.dart';

void main() {
  test('the live off shape parses, and off is a reported fact', () {
    final s = RemoteSurface.fromJson(const {
      'reported': true,
      'configured': false,
      'reason': 'RELAY_REMOTE_TOKEN is unset, so the remote surface stays off',
      'env_file': '.env',
      'env_file_found': false,
      'oauth_configured': false,
      'oauth_missing': [
        'RELAY_OAUTH_CLIENT_ID',
        'RELAY_OAUTH_CLIENT_SECRET',
        'RELAY_OAUTH_SIGNING_SECRET',
        'RELAY_PUBLIC_URL',
        'RELAY_AUTHORIZE_PASSWORD',
        'RELAY_OAUTH_REDIRECT_URIS',
      ],
      'tls_configured': false,
      'remote_exec_allowed': false,
      'public_url': null,
      'allowed_origins': [],
      'listen': {'host': null, 'port': null},
      'keys_present': {'RELAY_REMOTE_TOKEN': false},
    });
    expect(s.reach, RemoteReach.off);
    expect(s.reason, contains('RELAY_REMOTE_TOKEN'));
    expect(s.envFile, '.env');
    expect(s.envFileFound, isFalse);
    expect(s.oauthMissing, hasLength(6));
  });

  test('an unreachable lane is unknown, never off', () {
    // The distinction the card is built around. A lane that did not answer
    // says nothing about whether the surface is configured.
    final s = RemoteSurface.fromJson(const {
      'reported': false,
      'reason': 'relay lane unavailable: [WinError 2]',
    });
    expect(s.reach, RemoteReach.unknown);
    expect(s.configured, isFalse);
    expect(s.reason, contains('unavailable'));
  });

  test('an older relay build is unknown, and says which', () {
    final s = RemoteSurface.fromJson(const {
      'reported': false,
      'reason': 'this relay build does not report the remote surface',
    });
    expect(s.reach, RemoteReach.unknown);
    expect(s.reason, contains('does not report'));
  });

  test('serving with an incomplete oauth block reads as bearer only', () {
    // The trap. The server serves, nothing complains, and no phone pairs.
    final s = RemoteSurface.fromJson(const {
      'reported': true,
      'configured': true,
      'oauth_configured': false,
      'oauth_missing': ['RELAY_AUTHORIZE_PASSWORD'],
      'listen': {'host': '0.0.0.0', 'port': '8799'},
    });
    expect(s.reach, RemoteReach.bearerOnly);
    expect(s.oauthMissing, ['RELAY_AUTHORIZE_PASSWORD']);
  });

  test('a complete surface is paired', () {
    final s = RemoteSurface.fromJson(const {
      'reported': true,
      'configured': true,
      'oauth_configured': true,
      'oauth_missing': [],
      'tls_configured': true,
      'public_url': 'https://board.example',
      'allowed_origins': ['https://a.example', 'https://b.example'],
      'listen': {'host': '0.0.0.0', 'port': '8799'},
    });
    expect(s.reach, RemoteReach.paired);
    expect(s.publicUrl, 'https://board.example');
    expect(s.tlsConfigured, isTrue);
    expect(s.allowedOrigins, hasLength(2));
  });

  test('a value can never reach the view through keys_present', () {
    // The control. Presence is the contract, and relay enforces it. If a
    // future build regressed and sent a value here, this coerces it rather
    // than handing the view a secret to render.
    final s = RemoteSurface.fromJson(const {
      'reported': true,
      'configured': true,
      'keys_present': {
        'RELAY_REMOTE_TOKEN': 'sentinel-secret-value',
        'RELAY_TLS_CERT': true,
      },
    });
    expect(s.keysPresent['RELAY_REMOTE_TOKEN'], isFalse);
    // Not blanket-false. A key relay really did report as present still
    // reads as present, so the coercion cannot hide a configured surface
    // while appearing to protect it.
    expect(s.keysPresent['RELAY_TLS_CERT'], isTrue);
    // Every field the card can print, swept for the sentinel. A default
    // toString() would have passed this without reading anything.
    final printable = [
      s.reason, s.publicUrl, s.envFile, s.listen, s.listenHost, s.listenPort,
      ...s.allowedOrigins, ...s.oauthMissing, ...s.keysPresent.keys,
    ].join('|');
    expect(printable, isNot(contains('sentinel-secret-value')));
    // Not a vacuous sweep: the same join does catch a value when one is
    // carried by a field that is meant to carry values.
    final withUrl = RemoteSurface.fromJson(const {
      'reported': true,
      'public_url': 'sentinel-secret-value',
    });
    expect([withUrl.reason, withUrl.publicUrl].join('|'),
        contains('sentinel-secret-value'));
  });

  test('a null is absence, not the text "null"', () {
    final s = RemoteSurface.fromJson(const {
      'reported': true,
      'public_url': null,
      'env_file': null,
      'listen': {'host': null, 'port': null},
    });
    expect(s.publicUrl, '');
    expect(s.envFile, '');
    expect(s.listen, '');
  });

  test('an address is printed whole or not at all', () {
    // A host with no port is not something anyone can dial.
    expect(
        RemoteSurface.fromJson(const {
          'listen': {'host': '0.0.0.0'}
        }).listen,
        '');
    expect(
        RemoteSurface.fromJson(const {
          'listen': {'host': '0.0.0.0', 'port': '8799'}
        }).listen,
        '0.0.0.0:8799');
  });

  test('a wrongly typed payload degrades rather than crashing', () {
    final s = RemoteSurface.fromJson(const {
      'reported': 'yes',
      'oauth_missing': 'RELAY_OAUTH_CLIENT_ID',
      'allowed_origins': 7,
      'listen': 'localhost:8799',
      'keys_present': ['RELAY_REMOTE_TOKEN'],
    });
    // 'yes' is not true. A string where a flag belongs is not a flag.
    expect(s.reach, RemoteReach.unknown);
    expect(s.oauthMissing, isEmpty);
    expect(s.allowedOrigins, isEmpty);
    expect(s.listen, '');
    expect(s.keysPresent, isEmpty);
  });

  test('an empty payload is unknown, which is the safe default', () {
    expect(RemoteSurface.fromJson(const {}).reach, RemoteReach.unknown);
    expect(const RemoteSurface().reach, RemoteReach.unknown);
  });
}
