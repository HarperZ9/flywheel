import 'journey_models.dart';

final _previewRef = RegExp(r'^cpv_[0-9a-f]{32}$');

class ContinuationFailure {
  final String code;
  final String message;
  const ContinuationFailure(this.code, this.message);
}

class ContinuationApiException implements Exception {
  final ContinuationFailure failure;
  const ContinuationApiException(this.failure);
  @override
  String toString() => failure.message;
}

Map<String, Object?> _object(
    Object? raw, String field, List<ParseIssue> issues) {
  if (raw is Map<String, Object?>) return raw;
  if (raw is Map && raw.keys.every((key) => key is String)) {
    return Map<String, Object?>.from(raw);
  }
  addParseIssue(issues, field, raw);
  return const {};
}

String _localPath(Object? raw, String field, List<ParseIssue> issues) {
  if (raw is String && raw.isNotEmpty && isSafeLocalPath(raw)) return raw;
  addParseIssue(issues, field, raw);
  return '';
}

String? _optionalLocalPath(Object? raw, String field, List<ParseIssue> issues) {
  if (raw == null) return null;
  final value = _localPath(raw, field, issues);
  return value.isEmpty ? null : value;
}

class ContinuationDirtyFile extends DefensiveModel {
  final String path;
  final String status;
  final String? sha256;
  ContinuationDirtyFile._(
      this.path, this.status, this.sha256, super.parseIssues);
  factory ContinuationDirtyFile.fromJson(
      Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    final sha = readText(json, 'sha256', issues,
        optional: true, pattern: sha256Pattern);
    return ContinuationDirtyFile._(readText(json, 'path', issues),
        readText(json, 'status', issues), sha.isEmpty ? null : sha, issues);
  }
}

class ContinuationOmission extends DefensiveModel {
  final String code;
  final String detail;
  final String? pathHint;
  ContinuationOmission._(
      this.code, this.detail, this.pathHint, super.parseIssues);
  factory ContinuationOmission.fromJson(
      Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    final hint = readText(json, 'path_hint', issues, optional: true);
    return ContinuationOmission._(readText(json, 'code', issues),
        readDetail(json, 'detail', issues), hint.isEmpty ? null : hint, issues);
  }
}

class ContinuationRunnerContext extends DefensiveModel {
  final String root, goal;
  final List<String> selectedFiles;
  ContinuationRunnerContext._(
      this.root, this.goal, this.selectedFiles, super.parseIssues);
  factory ContinuationRunnerContext.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    return ContinuationRunnerContext._(
        _localPath(json['root'], 'runner_context.root', issues),
        readDetail(json, 'goal', issues),
        readStringList(
            json['selected_files'], 'runner_context.selected_files', issues),
        issues);
  }
}

class ContinuationPrivateContext extends DefensiveModel {
  final String previewRef, sourceStateSha256;
  final int selectedTaskCount;
  final List<String> selectedFiles;
  final ContinuationRunnerContext runner;
  ContinuationPrivateContext._(
      {required this.previewRef,
      required this.sourceStateSha256,
      required this.selectedTaskCount,
      required this.selectedFiles,
      required this.runner,
      required List<ParseIssue> parseIssues})
      : super(parseIssues);
  factory ContinuationPrivateContext.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(
        json, 'flywheel.native-continuation-private-context/v1', issues);
    final context = _object(json['context_package'], 'context_package', issues);
    final runner = ContinuationRunnerContext.fromJson(
        _object(json['runner_context'], 'runner_context', issues));
    issues.addAll(runner.parseIssues);
    return ContinuationPrivateContext._(
        previewRef: readText(json, 'preview_ref', issues, pattern: _previewRef),
        sourceStateSha256: readText(json, 'source_state_sha256', issues,
            pattern: sha256Pattern),
        selectedTaskCount:
            readStringList(context['selected_tasks'], 'selected_tasks', issues)
                .length,
        selectedFiles:
            readStringList(context['selected_files'], 'selected_files', issues),
        runner: runner,
        parseIssues: issues);
  }
}

class ContinuationPreview extends DefensiveModel {
  final String previewRef, previewSha256, sourceStateSha256, intakeRef;
  final String root;
  final String? exportPath;
  final String branch, head, providerNativeState, providerNativeReason;
  final String healthState;
  final List<String> blockingOmissions;
  final List<String> selectedFiles;
  final int mappingCount, dropCount, signalCount, mcpServerCount;
  final int selectedTaskCount, selectedSummaryCount;
  final List<ContinuationDirtyFile> dirtyFiles;
  final List<ContinuationOmission> omissions;
  bool get readyToStart => healthState == 'ready';
  ContinuationPreview._({
    required this.previewRef,
    required this.previewSha256,
    required this.sourceStateSha256,
    required this.intakeRef,
    required this.root,
    required this.exportPath,
    required this.branch,
    required this.head,
    required this.providerNativeState,
    required this.providerNativeReason,
    required this.healthState,
    required this.blockingOmissions,
    required this.selectedFiles,
    required this.mappingCount,
    required this.dropCount,
    required this.signalCount,
    required this.mcpServerCount,
    required this.selectedTaskCount,
    required this.selectedSummaryCount,
    required this.dirtyFiles,
    required this.omissions,
    required List<ParseIssue> parseIssues,
  }) : super(parseIssues);

  factory ContinuationPreview.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(json, 'flywheel.native-continuation-preview/v1', issues);
    final source = _object(json['source'], 'source', issues);
    final repo = _object(json['repo'], 'repo', issues);
    final imported = _object(json['import'], 'import', issues);
    final export = _object(json['export'], 'export', issues);
    final context = _object(json['context_package'], 'context_package', issues);
    final provider = _object(
        json['provider_native_resume'], 'provider_native_resume', issues);
    final health = _object(json['health'], 'health', issues);
    final dirty = readRecords(repo['dirty_files'], 'repo.dirty_files', issues,
        ContinuationDirtyFile.fromJson);
    final omissions = readRecords(
        json['omissions'], 'omissions', issues, ContinuationOmission.fromJson);
    issues.addAll(dirty.expand((item) => item.parseIssues));
    issues.addAll(omissions.expand((item) => item.parseIssues));
    return ContinuationPreview._(
      previewRef: readText(json, 'preview_ref', issues, pattern: _previewRef),
      previewSha256:
          readText(json, 'preview_sha256', issues, pattern: sha256Pattern),
      sourceStateSha256:
          readText(json, 'source_state_sha256', issues, pattern: sha256Pattern),
      intakeRef: readText(json, 'intake_ref', issues),
      root: _localPath(source['root'], 'source.root', issues),
      exportPath: _optionalLocalPath(
          source['export_path'], 'source.export_path', issues),
      branch: readDetail(repo, 'branch', issues),
      head: readText(repo, 'head', issues,
          optional: true, pattern: sha256Pattern),
      providerNativeState: readText(provider, 'state', issues),
      providerNativeReason: readDetail(provider, 'reason', issues),
      healthState: readText(health, 'state', issues),
      blockingOmissions: readStringList(
          health['blocking_omissions'], 'health.blocking_omissions', issues),
      selectedFiles:
          readStringList(context['selected_files'], 'selected_files', issues),
      mappingCount: (imported['mappings'] as List?)?.length ?? 0,
      dropCount: (imported['dropped'] as List?)?.length ?? 0,
      signalCount: (export['signals'] as List?)?.length ?? 0,
      mcpServerCount: readValue<int>(imported, 'mcp_server_count', issues, 0),
      selectedTaskCount:
          readStringList(context['selected_tasks'], 'selected_tasks', issues)
              .length,
      selectedSummaryCount: readStringList(
              context['selected_summaries'], 'selected_summaries', issues)
          .length,
      dirtyFiles: dirty,
      omissions: omissions,
      parseIssues: issues,
    );
  }
}

class ContinuationStartResult extends DefensiveModel {
  final JourneyMutationAck journey;
  final String previewRef;
  final JourneyLens openLens;
  ContinuationStartResult({
    required this.journey,
    required this.previewRef,
    required this.openLens,
  }) : super(const []);
  factory ContinuationStartResult.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(json, 'flywheel.native-continuation-start/v1', issues);
    final ack = JourneyMutationAck.fromJson(
        _object(json['journey'], 'journey', issues));
    issues.addAll(ack.parseIssues);
    final lens = json['open_lens'] == 'Rescue'
        ? JourneyLens.rescue
        : JourneyLens.invalidResponse;
    if (lens == JourneyLens.invalidResponse) {
      addParseIssue(issues, 'open_lens', json['open_lens']);
    }
    return ContinuationStartResult._(
        ack,
        readText(json, 'preview_ref', issues, pattern: _previewRef),
        lens,
        issues);
  }
  ContinuationStartResult._(
      this.journey, this.previewRef, this.openLens, super.parseIssues);
}

class ContinuationUndoResult extends DefensiveModel {
  final JourneyMutationAck journey;
  ContinuationUndoResult._(this.journey, super.parseIssues);
  factory ContinuationUndoResult.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(json, 'flywheel.native-continuation-undo/v1', issues);
    final ack = JourneyMutationAck.fromJson(
        _object(json['journey'], 'journey', issues));
    issues.addAll(ack.parseIssues);
    return ContinuationUndoResult._(ack, issues);
  }
}
