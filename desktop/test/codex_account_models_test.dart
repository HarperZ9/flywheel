import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/codex_account_models.dart';

void main() {
  test('account doc separates ChatGPT subscription from API billing', () {
    final doc = CodexAccountDoc.fromJson({
      'state': 'ready',
      'account': {
        'consumer': {
          'state': 'authenticated',
          'type': 'chatgpt',
          'plan_type': 'plus',
          'email_present': true,
        },
        'api_key': {'state': 'present', 'source': 'env:OPENAI_API_KEY'},
        'effective_auth_source': 'api-key',
        'usable_for_codex': true,
        'reason': '',
      },
      'capabilities': {'web_search': true},
    });

    expect(doc.phase, CodexAccountPhase.signedIn);
    expect(doc.chatGptSignedIn, isTrue);
    expect(doc.apiKeyPresent, isTrue);
    expect(doc.primaryRouteLabel, 'OpenAI API billing route');
    expect(doc.chatGptLabel, 'ChatGPT Plus account ready');
    expect(doc.capabilities.webSearch, isTrue);
  });

  test('unknown account state is unavailable, never signed in', () {
    final doc = CodexAccountDoc.fromJson({
      'state': 'unavailable',
      'reason': 'route not mounted',
      'account': {
        'consumer': {'state': 'unknown'},
        'api_key': {'state': 'unknown'},
        'effective_auth_source': 'unknown',
        'usable_for_codex': false,
      },
    });

    expect(doc.phase, CodexAccountPhase.unavailable);
    expect(doc.chatGptSignedIn, isFalse);
    expect(doc.apiKeyPresent, isFalse);
    expect(doc.primaryRouteLabel, 'Codex account unavailable');
  });

  test('login start accepts only exact HTTPS OpenAI or ChatGPT URLs', () {
    final good = CodexLoginStart.fromJson({
      'state': 'login_started',
      'mode': 'browser',
      'login_id': 'login_abc123',
      'auth_url': 'https://chatgpt.com/auth/device?client=codex',
    });
    expect(good.loginId, 'login_abc123');
    expect(good.launchUri?.toString(),
        'https://chatgpt.com/auth/device?client=codex');

    for (final url in [
      'http://chatgpt.com/auth',
      'https://example.invalid/auth',
      'https://chatgpt.com/auth?password=placeholder',
      'https://openai.com/auth\\evil',
    ]) {
      final rejected = CodexLoginStart.fromJson({
        'state': 'login_started',
        'mode': 'browser',
        'login_id': 'login_abc123',
        'auth_url': url,
      });
      expect(rejected.launchUri, isNull, reason: url);
    }
  });

  test('login start rejects credential-shaped URL values and fragments', () {
    for (final url in [
      'https://chatgpt.com/auth/codex?state=sk-private123456',
      'https://chatgpt.com/auth/codex?state=sk%2Dprivate123456',
      'https://openai.com/device#Bearer%20abcdefghijk',
      'https://openai.com/device#state=access_token%3Dabc123456',
    ]) {
      final rejected = CodexLoginStart.fromJson({
        'state': 'login_started',
        'mode': 'browser',
        'login_id': 'login_abc123',
        'auth_url': url,
      });
      expect(rejected.launchUri, isNull, reason: url);
    }
  });

  test('model catalog preserves authoritative no-manual unavailable state', () {
    final catalog = CodexModelCatalog.fromJson({
      'schema': 'flywheel.model-roster/v1',
      'endpoint': 'codex-cli',
      'allow_manual': false,
      'listing_authoritative': false,
      'reason': 'Codex account not authenticated',
      'models': [],
    });

    expect(catalog.allowManual, isFalse);
    expect(catalog.listingAuthoritative, isFalse);
    expect(catalog.models, isEmpty);
    expect(catalog.reason, contains('not authenticated'));
  });
}
