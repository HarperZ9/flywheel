import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';

import 'gateway_agent_execution_review_fixtures.dart';

void main() {
  test('local stub review has no network URL', () {
    final review = {
      ...gatewayAgentExecutionReview,
      'endpoint': 'stub',
      'base_url': '',
      'model': {
        'model_id': 'stub',
        'requested_model_reference': null,
        'selection': 'frozen_default',
        'observation_policy': 'unavailable',
        'profile': null,
      },
    };
    final parsed = GatewayAgentExecutionReview.fromJson(review, 'review');
    expect(parsed.invalidResponse, isFalse, reason: parsed.parseIssues.toString());
    expect(parsed.baseUrl, isEmpty);
    expect(parsed.model.modelId, 'stub');
    final networkStub = GatewayAgentExecutionReview.fromJson(
        {...review, 'base_url': 'https://example.invalid/v1'}, 'review');
    expect(networkStub.invalidResponse, isTrue);
  });

  test('API endpoint still requires a network URL', () {
    for (final endpoint in ['ollama', 'openai', 'stub-other']) {
      final parsed = GatewayAgentExecutionReview.fromJson({
        ...gatewayAgentExecutionReview,
        'endpoint': endpoint,
        'base_url': '',
      }, 'review');
      expect(parsed.invalidResponse, isTrue, reason: endpoint);
      expect(parsed.parseIssues.any((issue) => issue.field == 'base_url'), isTrue);
    }
  });
}
