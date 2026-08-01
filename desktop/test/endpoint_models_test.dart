// Subscription-first endpoint models: HostedTier/EndpointHealthDoc surface the
// paid-for CLI tier and degrade gracefully against an older gateway.

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/endpoint_models.dart';

void main() {
  test('HostedTier reads subscription-first fields', () {
    final h = HostedTier.fromJson({
      'name': 'claude',
      'model': 'claude-sonnet-5',
      'credential_present': false,
      'key_env': 'ANTHROPIC_API_KEY',
      'access': 'subscription',
      'subscription_present': true,
      'subscription_cli': 'claude.exe',
    });
    expect(h.access, 'subscription');
    expect(h.subscriptionPresent, isTrue);
    expect(h.usable, isTrue);
    expect(h.credentialPresent, isFalse); // usable with no API key
  });

  test('HostedTier degrades when the gateway predates the fields', () {
    final keyed = HostedTier.fromJson({
      'name': 'gemini',
      'credential_present': true,
      'key_env': 'GEMINI_API_KEY',
    });
    expect(keyed.access, 'api'); // inferred from credential presence
    expect(keyed.subscriptionPresent, isFalse);

    final none =
        HostedTier.fromJson({'name': 'deepseek', 'credential_present': false});
    expect(none.access, 'none');
    expect(none.usable, isFalse);
  });

  test('EndpointHealthDoc reads subscription counts', () {
    final d = EndpointHealthDoc.fromJson({
      'local': [],
      'enterprise': [
        {'name': 'claude', 'access': 'subscription', 'subscription_present': true},
        {'name': 'codex', 'access': 'subscription', 'subscription_present': true},
      ],
      'subscription_available': 2,
      'enterprise_usable': 2,
    });
    expect(d.subscriptionAvailable, 2);
    expect(d.enterpriseUsable, 2);
    expect(d.hosted.where((h) => h.usable).length, 2);
  });
}
