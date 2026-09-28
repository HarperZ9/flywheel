import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/codex_account_client.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/codex_account_models.dart';

void main() {
  test('codex account mutation POSTs do not follow redirects', () async {
    final followRedirects = <String, bool>{};
    final bodies = <String, Object?>{};
    final gateway = GatewayClient(
      baseUrl: 'http://127.0.0.1:8799',
      httpClient: MockClient((request) async {
        followRedirects[request.url.path] = request.followRedirects;
        bodies[request.url.path] = jsonDecode(request.body);
        return http.Response(jsonEncode(_responseFor(request.url.path)), 200);
      }),
    );
    final client = GatewayCodexAccountClient(gateway);

    await client.startLogin(CodexLoginMode.browser);
    await client.cancelLogin('login-1');
    await client.logout();

    expect(followRedirects, {
      '/api/codex/account/login/start': false,
      '/api/codex/account/login/cancel': false,
      '/api/codex/account/logout': false,
    });
    expect(bodies, {
      '/api/codex/account/login/start': {'mode': 'browser'},
      '/api/codex/account/login/cancel': {'login_id': 'login-1'},
      '/api/codex/account/logout': {},
    });
  });

  test('codex account client accepts backend 202 start and pending result',
      () async {
    final gateway = GatewayClient(
      baseUrl: 'http://127.0.0.1:8799',
      httpClient: MockClient((request) async {
        if (request.url.path.endsWith('/login/start')) {
          return http.Response(
            jsonEncode({
              'schema': 'flywheel.codex-account-route/v1',
              'provider': 'codex',
              'transport': 'codex-app-server',
              'state': 'login_started',
              'mode': 'browser',
              'login_id': 'login-202',
              'auth_url': 'https://chatgpt.com/auth/codex',
              'expires_at': 1790000000.0,
            }),
            202,
          );
        }
        return http.Response(
          jsonEncode({
            'schema': 'flywheel.codex-account-route/v1',
            'provider': 'codex',
            'transport': 'codex-app-server',
            'state': 'pending',
            'login_id': 'login-202',
            'completion_state': 'pending',
            'reason': 'waiting for account/login/completed',
          }),
          202,
        );
      }),
    );
    final client = GatewayCodexAccountClient(gateway);

    final start = await client.startLogin(CodexLoginMode.browser);
    final result = await client.loginResult(start.loginId);

    expect(start.loginId, 'login-202');
    expect(start.launchUri?.host, 'chatgpt.com');
    expect(result.pending, isTrue);
  });

  test('codex account client rejects unexpected status codes', () async {
    final gateway = GatewayClient(
      baseUrl: 'http://127.0.0.1:8799',
      httpClient: MockClient((request) async => http.Response(
            jsonEncode({
              'schema': 'flywheel.codex-account-route/v1',
              'state': request.url.path.endsWith('/login/start')
                  ? 'already_pending'
                  : 'redirect',
            }),
            request.url.path.endsWith('/login/start') ? 409 : 302,
          )),
    );
    final client = GatewayCodexAccountClient(gateway);

    await expectLater(
      client.startLogin(CodexLoginMode.browser),
      throwsA(isA<GatewayException>()),
    );
    await expectLater(
      client.loginResult('login-202'),
      throwsA(isA<GatewayException>()),
    );
  });
}

Map<String, Object?> _responseFor(String path) {
  if (path.endsWith('/login/start')) {
    return {
      'state': 'login_started',
      'mode': 'browser',
      'login_id': 'login-1',
      'auth_url': 'https://chatgpt.com/auth/codex',
    };
  }
  if (path.endsWith('/login/cancel')) {
    return {'state': 'cancelled', 'login_id': 'login-1'};
  }
  return {'state': 'logout_requested'};
}
