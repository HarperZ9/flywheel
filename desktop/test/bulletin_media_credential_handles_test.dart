import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/bulletin_media_api.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:http/http.dart' as http;

import 'bulletin_media_canonical_backend_test_support.dart';
import 'bulletin_media_test_support.dart';

void main() {
  test('gateway client lists safe Bulletin credential handle metadata',
      () async {
    final backend = await startCanonicalBackend(
      runId: 'run_20260909T000000_alpha',
      title: 'alpha root fixture',
      credentialHandleResponse: const {
        'schema': 'flywheel.credential-handle-list/v1',
        'handles': [
          {'credential_ref': credRef, 'credential_name': 'BULLETIN_AGENT_JWK'},
          {
            'credential_ref': 'cred_11111111111111111111111111111111',
            'credential_name': 'OTHER_SLOT'
          }
        ]
      },
    );
    final client =
        GatewayClient(baseUrl: backend.baseUrl, httpClient: http.Client());
    try {
      final handles = await GatewayBulletinMediaApi(client).credentialHandles();
      expect(handles, hasLength(1));
      expect(handles.single.credentialRef, credRef);
      expect(handles.single.credentialName, 'BULLETIN_AGENT_JWK');
      expect(backend.paths, ['/api/credential-handles']);
    } finally {
      client.close();
      await backend.close();
    }
  });

  test('gateway client rejects credential rows with secret-like values',
      () async {
    final backend = await startCanonicalBackend(
      runId: 'run_20260909T000000_alpha',
      title: 'alpha root fixture',
      credentialHandleResponse: const {
        'schema': 'flywheel.credential-handle-list/v1',
        'handles': [
          {
            'credential_ref': credRef,
            'credential_name': 'BULLETIN_AGENT_JWK',
            'value': 'secret-value'
          }
        ]
      },
    );
    final client =
        GatewayClient(baseUrl: backend.baseUrl, httpClient: http.Client());
    try {
      await expectLater(GatewayBulletinMediaApi(client).credentialHandles(),
          throwsA(isA<FormatException>()));
    } finally {
      client.close();
      await backend.close();
    }
  });
}
