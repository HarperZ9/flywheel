import 'package:flutter/foundation.dart';

import '../models/operation_models.dart';
import '../models/rowan_walkthrough_models.dart';

final class RowanWalkthroughController extends ChangeNotifier {
  RowanWalkthroughController({required this.scenario});

  final RowanWalkthroughScenario scenario;
  RowanWalkthroughCheckpoint _checkpoint = RowanWalkthroughCheckpoint.readiness;
  RowanWalkthroughOracle _oracle = const RowanWalkthroughOracle(
    RowanWalkthroughOracleState.waiting,
    'The oracle runs only after a terminal result is available.',
  );
  RowanWalkthroughOutcome? _outcome;
  String? _terminalOperationRef;
  String? _terminalResultSha256;
  String? _lastJourneyRef;
  String? _lastEventHeadSha256;

  RowanWalkthroughCheckpoint get checkpoint => _checkpoint;
  RowanWalkthroughOracle get oracle => _oracle;
  RowanWalkthroughOutcome? get outcome => _outcome;
  String? get terminalOperationRef => _terminalOperationRef;
  String? get terminalResultSha256 => _terminalResultSha256;
  String? get lastJourneyRef => _lastJourneyRef;
  String? get lastEventHeadSha256 => _lastEventHeadSha256;
  bool get canPrepareFollowUp =>
      _checkpoint == RowanWalkthroughCheckpoint.reopened && _oracle.passed;

  void markReviewPrepared() {
    _checkpoint = RowanWalkthroughCheckpoint.review;
    _outcome = null;
    notifyListeners();
  }

  void beginExecution() {
    _terminalOperationRef = null;
    _terminalResultSha256 = null;
    _lastJourneyRef = null;
    _lastEventHeadSha256 = null;
    _checkpoint = RowanWalkthroughCheckpoint.running;
    _oracle = const RowanWalkthroughOracle(
      RowanWalkthroughOracleState.waiting,
      'The oracle runs only after a terminal result is available.',
    );
    _outcome = null;
    notifyListeners();
  }

  void markDenied() {
    if (_checkpoint.index < RowanWalkthroughCheckpoint.review.index) {
      _checkpoint = RowanWalkthroughCheckpoint.review;
    }
    _outcome = RowanWalkthroughOutcome.denied;
    notifyListeners();
  }

  void markInterrupted() {
    _outcome = RowanWalkthroughOutcome.interrupted;
    notifyListeners();
  }

  void markMissingRecord() {
    _outcome = RowanWalkthroughOutcome.missingRecord;
    notifyListeners();
  }

  void acceptTerminalResult(OperationResult result,
      {OperationSnapshot? snapshot}) {
    _terminalOperationRef = result.operationRef;
    _terminalResultSha256 = result.canonicalSha256;
    if (snapshot != null) _rememberSnapshot(snapshot);
    _oracle = scenario.evaluate(result.result);
    _checkpoint = RowanWalkthroughCheckpoint.semanticOracle;
    _outcome = _oracle.passed ? null : RowanWalkthroughOutcome.wrongAnswer;
    notifyListeners();
  }

  void markReopened(OperationSnapshot snapshot) {
    _rememberSnapshot(snapshot);
    if (!snapshot.isTerminal ||
        snapshot.operationRef != _terminalOperationRef ||
        snapshot.resultSha256 != _terminalResultSha256) {
      _outcome = RowanWalkthroughOutcome.missingRecord;
      notifyListeners();
      return;
    }
    if (!_oracle.passed) {
      _outcome = RowanWalkthroughOutcome.wrongAnswer;
      notifyListeners();
      return;
    }
    _checkpoint = RowanWalkthroughCheckpoint.reopened;
    _outcome = null;
    notifyListeners();
  }

  void _rememberSnapshot(OperationSnapshot snapshot) {
    _lastJourneyRef = snapshot.journeyRef;
    _lastEventHeadSha256 = snapshot.eventHeadSha256;
  }
}
