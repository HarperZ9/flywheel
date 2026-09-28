import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/codex_account_client.dart';
import 'package:flywheel_desktop/controllers/codex_account_controller.dart';
import 'package:flywheel_desktop/models/codex_account_models.dart';

void main() {
  test('refresh is read-only and does not start or end account sessions',
      () async {
    final api = _FakeCodexAccountApi(account: _signedOut());
    final c = CodexAccountController(api);

    await c.refresh();

    expect(api.reads, 1);
    expect(api.starts, isEmpty);
    expect(api.cancels, isEmpty);
    expect(api.logoutCalls, 0);
    expect(api.modelReads, 0);
    expect(c.phase, CodexAccountPhase.signedOut);
  });

  test('browser login is pending until exact result and readback complete',
      () async {
    final api = _FakeCodexAccountApi(account: _signedOut())
      ..startResponse = CodexLoginStart.fromJson({
        'state': 'login_started',
        'mode': 'browser',
        'login_id': 'login_exact',
        'auth_url': 'https://chatgpt.com/auth/codex',
      })
      ..resultResponse = CodexLoginResult.fromJson({
        'state': 'authenticated',
        'login_id': 'login_exact',
        'completion_state': 'completed',
      })
      ..accountAfterResult = _chatGptPlus()
      ..catalog = CodexModelCatalog.fromJson({
        'endpoint': 'codex-cli',
        'allow_manual': false,
        'listing_authoritative': true,
        'models': [
          {'id': 'gpt-5.6-sol', 'display_name': 'GPT 5.6 Sol'},
        ],
      });
    final c = CodexAccountController(api);

    await c.startLogin(CodexLoginMode.browser);
    expect(c.phase, CodexAccountPhase.loginPending);
    expect(api.starts, [CodexLoginMode.browser]);
    expect(api.resultLoginIds, isEmpty);

    await c.refreshLoginResult();

    expect(api.resultLoginIds, ['login_exact']);
    expect(c.phase, CodexAccountPhase.signedIn);
    expect(c.account?.chatGptSignedIn, isTrue);
    expect(c.catalog?.models.single.id, 'gpt-5.6-sol');
    expect(api.modelReads, 1);
  });

  test('authenticated completion without account readback is not success',
      () async {
    final api = _FakeCodexAccountApi(account: _signedOut())
      ..startResponse = CodexLoginStart.fromJson({
        'state': 'login_started',
        'mode': 'device_code',
        'login_id': 'login_device',
        'verification_url': 'https://openai.com/device',
        'user_code': 'ABCD-EFGH',
      })
      ..resultResponse = CodexLoginResult.fromJson({
        'state': 'authenticated',
        'login_id': 'login_device',
      })
      ..accountAfterResult = _signedOut();
    final c = CodexAccountController(api);

    await c.startLogin(CodexLoginMode.deviceCode);
    await c.refreshLoginResult();

    expect(c.phase, CodexAccountPhase.failed);
    expect(c.message, contains('Account readback'));
    expect(api.modelReads, 0);
  });

  test('consumer login completion cannot use API-key-only readback', () async {
    final api = _FakeCodexAccountApi(account: _signedOut())
      ..startResponse = CodexLoginStart.fromJson({
        'state': 'login_started',
        'mode': 'browser',
        'login_id': 'login_api_key_only',
        'auth_url': 'https://chatgpt.com/auth/codex',
      })
      ..resultResponse = CodexLoginResult.fromJson({
        'state': 'authenticated',
        'login_id': 'login_api_key_only',
        'completion_state': 'completed',
      })
      ..accountAfterResult = CodexAccountDoc.fromJson({
        'state': 'ready',
        'account': {
          'consumer': {'state': 'not_authenticated', 'type': 'chatgpt'},
          'api_key': {'state': 'present', 'source': 'env:OPENAI_API_KEY'},
          'effective_auth_source': 'api-key',
          'usable_for_codex': true,
        },
      })
      ..catalog = CodexModelCatalog.fromJson({
        'models': [
          {'id': 'gpt-5.6-sol'},
        ],
      });
    final c = CodexAccountController(api);

    await c.startLogin(CodexLoginMode.browser);
    final ready = await c.refreshLoginResult();

    expect(ready, isFalse);
    expect(c.phase, CodexAccountPhase.failed);
    expect(c.login?.loginId, 'login_api_key_only');
    expect(api.modelReads, 0);
  });

  test('mismatched login result id does not consume account readback',
      () async {
    final api = _FakeCodexAccountApi(account: _signedOut())
      ..startResponse = CodexLoginStart.fromJson({
        'state': 'login_started',
        'mode': 'browser',
        'login_id': 'login_active',
        'auth_url': 'https://chatgpt.com/auth/codex',
      })
      ..resultResponse = CodexLoginResult.fromJson({
        'state': 'authenticated',
        'login_id': 'login_other',
      })
      ..accountAfterResult = _chatGptPlus();
    final c = CodexAccountController(api);

    await c.startLogin(CodexLoginMode.browser);
    await c.refreshLoginResult();

    expect(api.resultLoginIds, ['login_active']);
    expect(api.reads, 0);
    expect(api.modelReads, 0);
    expect(c.phase, CodexAccountPhase.failed);
    expect(c.message, contains('active login id'));
  });

  test('cancel and logout use explicit operations only', () async {
    final api = _FakeCodexAccountApi(account: _chatGptPlus())
      ..startResponse = CodexLoginStart.fromJson({
        'state': 'login_started',
        'mode': 'browser',
        'login_id': 'login_cancel',
        'auth_url': 'https://chatgpt.com/auth/codex',
      });
    final c = CodexAccountController(api);

    await c.startLogin(CodexLoginMode.browser);
    await c.cancelLogin();
    await c.logout();

    expect(api.cancels, ['login_cancel']);
    expect(api.logoutCalls, 1);
  });

  test('disposed controller ignores late refresh responses', () async {
    final completer = Completer<CodexAccountDoc>();
    final api = _FakeCodexAccountApi.pending(completer.future);
    final c = CodexAccountController(api);
    var notifications = 0;
    c.addListener(() => notifications++);

    final pending = c.refresh();
    c.dispose();
    completer.complete(_chatGptPlus());
    await pending;

    expect(notifications, 1, reason: 'only the initial busy state notifies');
  });
}

CodexAccountDoc _signedOut() => CodexAccountDoc.fromJson({
      'state': 'ready',
      'account': {
        'consumer': {'state': 'not_authenticated', 'plan_type': 'unknown'},
        'api_key': {'state': 'absent'},
        'effective_auth_source': 'none',
        'usable_for_codex': false,
        'reason': 'Codex account not authenticated',
      },
    });

CodexAccountDoc _chatGptPlus() => CodexAccountDoc.fromJson({
      'state': 'ready',
      'account': {
        'consumer': {
          'state': 'authenticated',
          'type': 'chatgpt',
          'plan_type': 'plus',
        },
        'api_key': {'state': 'absent'},
        'effective_auth_source': 'consumer-chatgpt',
        'usable_for_codex': true,
      },
    });

class _FakeCodexAccountApi implements CodexAccountApi {
  _FakeCodexAccountApi({required this.account});
  _FakeCodexAccountApi.pending(this.pendingAccount);

  CodexAccountDoc? account;
  Future<CodexAccountDoc>? pendingAccount;
  CodexAccountDoc? accountAfterResult;
  CodexLoginStart startResponse = CodexLoginStart.fromJson({});
  CodexLoginResult resultResponse = CodexLoginResult.fromJson({});
  CodexModelCatalog catalog = CodexModelCatalog.empty();
  final starts = <CodexLoginMode>[];
  final cancels = <String>[];
  final resultLoginIds = <String>[];
  var reads = 0;
  var modelReads = 0;
  var logoutCalls = 0;

  @override
  Future<CodexAccountDoc> readAccount() async {
    reads++;
    if (pendingAccount != null) return pendingAccount!;
    final next = accountAfterResult ?? account;
    accountAfterResult = null;
    return next!;
  }

  @override
  Future<CodexLoginStart> startLogin(CodexLoginMode mode) async {
    starts.add(mode);
    return startResponse;
  }

  @override
  Future<CodexLoginResult> loginResult(String loginId) async {
    resultLoginIds.add(loginId);
    return resultResponse;
  }

  @override
  Future<CodexLoginResult> cancelLogin(String loginId) async {
    cancels.add(loginId);
    return CodexLoginResult.fromJson({'state': 'canceled'});
  }

  @override
  Future<CodexLoginResult> logout() async {
    logoutCalls++;
    return CodexLoginResult.fromJson({'state': 'logout_requested'});
  }

  @override
  Future<CodexModelCatalog> readModelCatalog() async {
    modelReads++;
    return catalog;
  }
}
