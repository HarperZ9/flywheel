import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';

void main() {
  test('Bulletin identity create uses typed route and confirmation', () async {
    Uri? seenUrl;
    Map<String, dynamic>? seenBody;
    final client = GatewayClient(
      httpClient: MockClient((request) async {
        seenUrl = request.url;
        seenBody = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
            jsonEncode({'ok': true, 'action': 'created_stored'}), 200);
      }),
    );

    final result = await client.bulletinIdentityCreate();

    expect(seenUrl!.path, '/api/bulletin-identity/create');
    expect(seenBody, {
      'schema': 'flywheel.bulletin-identity-create-request/v1',
      'action': 'create',
      'confirm_create': true,
    });
    expect(result['action'], 'created_stored');
  });

  test('Bulletin identity register uses fixed typed route and confirmation',
      () async {
    Uri? seenUrl;
    Map<String, dynamic>? seenBody;
    final client = GatewayClient(
      httpClient: MockClient((request) async {
        seenUrl = request.url;
        seenBody = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
            jsonEncode({'ok': true, 'action': 'registered'}), 200);
      }),
    );

    final result = await client.bulletinIdentityRegister();

    expect(seenUrl!.path, '/api/bulletin-identity/register');
    expect(seenBody, {
      'schema': 'flywheel.bulletin-identity-register-request/v1',
      'action': 'register',
      'confirm_register': true,
    });
    expect(result['action'], 'registered');
  });
}
