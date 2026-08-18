part of 'gateway_client.dart';

extension GatewayPlanTransport on GatewayClient {
  Future<Map<String, dynamic>> postPlanJson(
      String path, Map<String, dynamic> body) async {
    final response = await _http.post(
      Uri.parse('$baseUrl$path'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (response.statusCode != 200) {
      throw GatewayException.fromResponse(response.statusCode, response.body);
    }
    return strictPlanJsonObject(response.bodyBytes);
  }
}
