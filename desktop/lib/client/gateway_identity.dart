part of 'gateway_client.dart';

extension GatewayIdentityClient on GatewayClient {
  Future<Map<String, dynamic>> bulletinIdentityStatus() =>
      getJson('/api/bulletin-identity');

  Future<Map<String, dynamic>> bulletinIdentityCreate() => postJsonLenient(
        '/api/bulletin-identity/create',
        const {
          'schema': 'flywheel.bulletin-identity-create-request/v1',
          'action': 'create',
          'confirm_create': true,
        },
      );

  Future<Map<String, dynamic>> bulletinIdentityRegister() => postJsonLenient(
        '/api/bulletin-identity/register',
        const {
          'schema': 'flywheel.bulletin-identity-register-request/v1',
          'action': 'register',
          'confirm_register': true,
        },
      );
}
