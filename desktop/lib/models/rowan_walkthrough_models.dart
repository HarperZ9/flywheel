import 'dart:convert';

import 'package:crypto/crypto.dart';

enum RowanWalkthroughCheckpoint {
  readiness,
  review,
  running,
  semanticOracle,
  reopened;
}

enum RowanWalkthroughOutcome {
  denied,
  interrupted,
  missingRecord,
  wrongAnswer,
}

enum RowanWalkthroughOracleState {
  waiting,
  passed,
  failed,
  unavailable,
}

final class RowanWalkthroughOracle {
  const RowanWalkthroughOracle(this.state, this.message, {this.resultSha256});

  final RowanWalkthroughOracleState state;
  final String message;
  final String? resultSha256;

  bool get passed => state == RowanWalkthroughOracleState.passed;
}

final class RowanWalkthroughScenario {
  const RowanWalkthroughScenario({
    required this.scenarioId,
    required this.version,
    required this.title,
    required this.goal,
    required this.maxSteps,
    required this.maxTokens,
    required this.timeoutSeconds,
  });

  final String scenarioId, version, title, goal;
  final int maxSteps, maxTokens, timeoutSeconds;

  RowanWalkthroughOracle evaluate(Map<String, Object?> result) {
    final finalText = result['final'];
    if (finalText is! String || finalText.trim().isEmpty) {
      return const RowanWalkthroughOracle(
        RowanWalkthroughOracleState.unavailable,
        'The terminal result did not include a readable final answer.',
      );
    }
    final text = finalText.toLowerCase();
    final namesDefect =
        text.contains('off-by-one') || text.contains('off by one');
    final namesBoundary =
        text.contains('attempt 4') || text.contains('next_attempt');
    final namesRule = text.contains('max_attempts') &&
        (text.contains('<= max_attempts') ||
            text.contains('<=max_attempts') ||
            text.contains('not max_attempts + 1'));
    final digest = sha256.convert(utf8.encode(finalText)).toString();
    if (namesDefect && namesBoundary && namesRule) {
      return RowanWalkthroughOracle(
        RowanWalkthroughOracleState.passed,
        'The independent oracle matched the defect and boundary case.',
        resultSha256: digest,
      );
    }
    return RowanWalkthroughOracle(
      RowanWalkthroughOracleState.failed,
      'The run completed, but the independent oracle did not accept the answer.',
      resultSha256: digest,
    );
  }
}

const rowanRetryPolicyWalkthroughScenario = RowanWalkthroughScenario(
  scenarioId: 'rowan.retry-policy.read-only',
  version: '2026-09-10.1',
  title: 'Retry policy read-only review',
  goal: 'Review the retry policy implementation in this workspace. Do not edit '
      'files. Report whether may_start_attempt obeys this rule: attempts are '
      'numbered from 1, and at most max_attempts attempts may start. Name the '
      'boundary case that decides it.',
  maxSteps: 3,
  maxTokens: 1024,
  timeoutSeconds: 300,
);
