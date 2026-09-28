// Gateway wrapper for the native Codex account helper routes.

import '../models/codex_account_models.dart';
import 'gateway_client.dart';

abstract class CodexAccountApi {
  Future<CodexAccountDoc> readAccount();
  Future<CodexLoginStart> startLogin(CodexLoginMode mode);
  Future<CodexLoginResult> loginResult(String loginId);
  Future<CodexLoginResult> cancelLogin(String loginId);
  Future<CodexLoginResult> logout();
  Future<CodexModelCatalog> readModelCatalog();
}

class GatewayCodexAccountClient implements CodexAccountApi {
  static const _startOrPendingStatuses = {200, 202};
  final GatewayClient gateway;
  const GatewayCodexAccountClient(this.gateway);

  @override
  Future<CodexAccountDoc> readAccount() async {
    try {
      return CodexAccountDoc.fromJson(
          await gateway.getJson('/api/codex/account'));
    } catch (e) {
      return CodexAccountDoc.unavailable(_safeFailure(e));
    }
  }

  @override
  Future<CodexLoginStart> startLogin(CodexLoginMode mode) async {
    final body = {
      'mode': mode == CodexLoginMode.browser ? 'browser' : 'device_code'
    };
    return CodexLoginStart.fromJson(await gateway.postJsonNoRedirect(
      '/api/codex/account/login/start',
      body,
      acceptedStatuses: _startOrPendingStatuses,
    ));
  }

  @override
  Future<CodexLoginResult> loginResult(String loginId) async {
    final q = Uri.encodeQueryComponent(loginId);
    return CodexLoginResult.fromJson(await gateway.getJson(
      '/api/codex/account/login/result?login_id=$q',
      acceptedStatuses: _startOrPendingStatuses,
    ));
  }

  @override
  Future<CodexLoginResult> cancelLogin(String loginId) async =>
      CodexLoginResult.fromJson(
        await gateway.postJsonNoRedirect(
            '/api/codex/account/login/cancel', {'login_id': loginId}),
      );

  @override
  Future<CodexLoginResult> logout() async => CodexLoginResult.fromJson(
        await gateway.postJsonNoRedirect('/api/codex/account/logout', const {}),
      );

  @override
  Future<CodexModelCatalog> readModelCatalog() async {
    try {
      return CodexModelCatalog.fromJson(await gateway.models('codex-cli'));
    } catch (e) {
      return CodexModelCatalog.empty(reason: _safeFailure(e));
    }
  }
}

String _safeFailure(Object error) {
  if (error is GatewayException) return error.message;
  return 'request failed: ${error.runtimeType}';
}
