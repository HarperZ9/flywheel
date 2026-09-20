import '../models/evidence_state.dart';
import '../models/operation_models.dart';
import 'rowan_action_cue_hash.dart';

const rowanActionCueSchema = 'flywheel.rowan-action-cue/v1';
final _eventRef = RegExp(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$');
final _journeyRef = RegExp(r'^jrn_[0-9a-f]{32}$');

enum RowanActionCueSource {
  operation,
  input,
  approval,
  connection,
  listening,
  screenSharing,
  evaluation,
  clarification,
  response,
  research,
  navigation,
  creative,
  correction,
  interruption,
  resume,
  latency,
  error,
  evidence,
  check,
  receipt,
  replay,
  thanks,
  screen,
  onboarding,
  chatNavigation,
  modelProvider,
  crossProviderOrchestration,
  privacyLivescreen,
  studioVisualAudio,
  codingTools,
  verificationReceipts,
  errorsRecovery,
  longTasksLimitsAccessibility,
  reactions,
  exportsPresentations,
}

final class RowanActionCueKind {
  const RowanActionCueKind.known(this.wire, this.defaultSource);

  final String wire;
  final RowanActionCueSource defaultSource;

  static const operationReady =
      RowanActionCueKind.known('operation.ready', RowanActionCueSource.operation);
  static const operationStarted = RowanActionCueKind.known(
      'operation.started', RowanActionCueSource.operation);
  static const operationWorking = RowanActionCueKind.known(
      'operation.working', RowanActionCueSource.operation);
  static const inputRequired =
      RowanActionCueKind.known('input.required', RowanActionCueSource.input);
  static const approvalWaiting = RowanActionCueKind.known(
      'approval.waiting', RowanActionCueSource.approval);
  static const operationPaused = RowanActionCueKind.known(
      'operation.paused', RowanActionCueSource.operation);
  static const operationResumed = RowanActionCueKind.known(
      'operation.resumed', RowanActionCueSource.operation);
  static const operationStopped = RowanActionCueKind.known(
      'operation.stopped', RowanActionCueSource.operation);
  static const operationCompleted = RowanActionCueKind.known(
      'operation.completed', RowanActionCueSource.operation);
  static const operationUnableToComplete = RowanActionCueKind.known(
      'operation.unable_to_complete', RowanActionCueSource.operation);
  static const connectionReconnecting = RowanActionCueKind.known(
      'connection.reconnecting', RowanActionCueSource.connection);
  static const connectionRestored = RowanActionCueKind.known(
      'connection.restored', RowanActionCueSource.connection);
  static const listeningStarted = RowanActionCueKind.known(
      'listening.started', RowanActionCueSource.listening);
  static const screenSharingStarted = RowanActionCueKind.known(
      'screen_sharing.started', RowanActionCueSource.screenSharing);
  static const screenSharingStopped = RowanActionCueKind.known(
      'screen_sharing.stopped', RowanActionCueSource.screenSharing);
  static const evaluationFinished = RowanActionCueKind.known(
      'evaluation.finished', RowanActionCueSource.evaluation);
  static const clarificationFocusFirst = RowanActionCueKind.known(
      'clarification.focus_first', RowanActionCueSource.clarification);
  static const clarificationDepthChoice = RowanActionCueKind.known(
      'clarification.depth_choice', RowanActionCueSource.clarification);
  static const responseConcise =
      RowanActionCueKind.known('response.concise', RowanActionCueSource.response);
  static const responseDetailOffer = RowanActionCueKind.known(
      'response.detail_offer', RowanActionCueSource.response);
  static const researchSourceChecking = RowanActionCueKind.known(
      'research.source_checking', RowanActionCueSource.research);
  static const researchEvidenceReading = RowanActionCueKind.known(
      'research.evidence_reading', RowanActionCueSource.research);
  static const researchResultChecking = RowanActionCueKind.known(
      'research.result_checking', RowanActionCueSource.research);
  static const navigationNextView = RowanActionCueKind.known(
      'navigation.next_view', RowanActionCueSource.navigation);
  static const creativeDifferentDirection = RowanActionCueKind.known(
      'creative.different_direction', RowanActionCueSource.creative);
  static const creativeReadyToCompare = RowanActionCueKind.known(
      'creative.ready_to_compare', RowanActionCueSource.creative);
  static const creativeCleanerPass = RowanActionCueKind.known(
      'creative.cleaner_pass', RowanActionCueSource.creative);
  static const correctionAccepted = RowanActionCueKind.known(
      'correction.accepted', RowanActionCueSource.correction);
  static const correctionAdjustCourse = RowanActionCueKind.known(
      'correction.adjust_course', RowanActionCueSource.correction);
  static const interruptionStopThere = RowanActionCueKind.known(
      'interruption.stop_there', RowanActionCueSource.interruption);
  static const resumeBackOnRun =
      RowanActionCueKind.known('resume.back_on_run', RowanActionCueSource.resume);
  static const resumeLastSavedState = RowanActionCueKind.known(
      'resume.last_saved_state', RowanActionCueSource.resume);
  static const latencyMoment =
      RowanActionCueKind.known('latency.moment', RowanActionCueSource.latency);
  static const latencyWaitingResponse = RowanActionCueKind.known(
      'latency.waiting_response', RowanActionCueSource.latency);
  static const latencySlowerService = RowanActionCueKind.known(
      'latency.slower_service', RowanActionCueSource.latency);
  static const errorRecoverablePath = RowanActionCueKind.known(
      'error.recoverable_path', RowanActionCueSource.error);
  static const errorNoResultReturned = RowanActionCueKind.known(
      'error.no_result_returned', RowanActionCueSource.error);
  static const evidenceReproductionFailed = RowanActionCueKind.known(
      'evidence.reproduction_failed', RowanActionCueSource.evidence);
  static const evidenceClaimMismatch = RowanActionCueKind.known(
      'evidence.claim_mismatch', RowanActionCueSource.evidence);
  static const evidenceCannotVerify = RowanActionCueKind.known(
      'evidence.cannot_verify', RowanActionCueSource.evidence);
  static const checkNamedPass =
      RowanActionCueKind.known('check.named_pass', RowanActionCueSource.check);
  static const checkMismatchFound = RowanActionCueKind.known(
      'check.mismatch_found', RowanActionCueSource.check);
  static const checkInconclusive =
      RowanActionCueKind.known('check.inconclusive', RowanActionCueSource.check);
  static const receiptSaved =
      RowanActionCueKind.known('receipt.saved', RowanActionCueSource.receipt);
  static const replayLabelVisible = RowanActionCueKind.known(
      'replay.label_visible', RowanActionCueSource.replay);
  static const thanksKeepGoing =
      RowanActionCueKind.known('thanks.keep_going', RowanActionCueSource.thanks);
  static const thanksWelcome =
      RowanActionCueKind.known('thanks.welcome', RowanActionCueSource.thanks);
  static const clarificationHelpsContinue = RowanActionCueKind.known(
      'clarification.helps_continue', RowanActionCueSource.clarification);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RowanActionCueKind && other.wire == wire;

  @override
  int get hashCode => wire.hashCode;

  @override
  String toString() => 'RowanActionCueKind($wire)';
}

enum RowanActionScreen { assistantPanel, walkthrough }

extension RowanActionScreenWire on RowanActionScreen {
  String get wire => switch (this) {
        RowanActionScreen.assistantPanel => 'assistant_panel',
        RowanActionScreen.walkthrough => 'walkthrough',
      };
}

class RowanActionCueEvent {
  const RowanActionCueEvent._({
    required this.kind,
    required this.source,
    required this.eventRef,
    this.operationRef,
    this.journeyRef,
    this.eventHeadSha256,
    this.screen,
    this.recovered = false,
  });

  factory RowanActionCueEvent.fromOperationSnapshot(
    OperationSnapshot snapshot, {
    bool recovered = false,
  }) {
    final kind = switch (snapshot.state) {
      OperationState.queued => RowanActionCueKind.operationStarted,
      OperationState.running ||
      OperationState.cancelRequested =>
        RowanActionCueKind.operationWorking,
      OperationState.completed => RowanActionCueKind.operationCompleted,
      OperationState.failed => RowanActionCueKind.operationUnableToComplete,
      OperationState.cancelled => RowanActionCueKind.operationStopped,
      _ => throw ArgumentError('operation state cannot cue playback'),
    };
    return RowanActionCueEvent._(
      kind: kind,
      source: RowanActionCueSource.operation,
      eventRef: snapshot.terminalEventRef ?? snapshot.eventHeadSha256,
      operationRef: snapshot.operationRef,
      journeyRef: snapshot.journeyRef,
      eventHeadSha256: snapshot.eventHeadSha256,
      recovered: recovered,
    );
  }

  factory RowanActionCueEvent.fromScreen({
    required RowanActionScreen screen,
    required String eventRef,
    bool recovered = false,
  }) {
    _validateEventRef(eventRef);
    return RowanActionCueEvent._(
      kind: RowanActionCueKind.operationReady,
      source: RowanActionCueSource.screen,
      eventRef: eventRef,
      screen: screen,
      recovered: recovered,
    );
  }

  factory RowanActionCueEvent.fromStableEvent({
    required RowanActionCueKind kind,
    required String eventRef,
    String? operationRef,
    String? journeyRef,
    String? eventHeadSha256,
    bool recovered = false,
  }) {
    _validateEventRef(eventRef);
    _validateOptionalBinding(operationRef, journeyRef, eventHeadSha256);
    return RowanActionCueEvent._(
      kind: kind,
      source: kind.defaultSource,
      eventRef: eventRef,
      operationRef: operationRef,
      journeyRef: journeyRef,
      eventHeadSha256: eventHeadSha256,
      recovered: recovered,
    );
  }

  final RowanActionCueKind kind;
  final RowanActionCueSource source;
  final String eventRef;
  final String? operationRef, journeyRef, eventHeadSha256;
  final RowanActionScreen? screen;
  final bool recovered;

  String get _subjectRef => operationRef ?? screen?.wire ?? source.name;
  String get dedupeKey => '${source.name}:$_subjectRef:$eventRef:${kind.wire}';
  String get cooldownKey => '${source.name}:$_subjectRef:${kind.wire}';

  Map<String, Object?> toJson() => {
        'schema': rowanActionCueSchema,
        'kind': kind.wire,
        'source': source.name,
        'event_ref': eventRef,
        'operation_ref': operationRef,
        'journey_ref': journeyRef,
        'event_head_sha256': eventHeadSha256,
        'screen': screen?.wire,
        'recovered': recovered,
      };

  String get eventSha256 => rowanActionCueSha256(toJson());
}

void _validateEventRef(String eventRef) {
  if (!_eventRef.hasMatch(eventRef)) throw ArgumentError('invalid eventRef');
}

void _validateOptionalBinding(
  String? operationRef,
  String? journeyRef,
  String? eventHeadSha256,
) {
  if (operationRef != null && !operationRefPattern.hasMatch(operationRef)) {
    throw ArgumentError('invalid operationRef');
  }
  if (journeyRef != null && !_journeyRef.hasMatch(journeyRef)) {
    throw ArgumentError('invalid journeyRef');
  }
  if (eventHeadSha256 != null && !sha256Pattern.hasMatch(eventHeadSha256)) {
    throw ArgumentError('invalid eventHeadSha256');
  }
}
