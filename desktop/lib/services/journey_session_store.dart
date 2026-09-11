import 'dart:collection';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

import '../client/gateway_auth.dart';
import '../models/evidence_state.dart';

part 'journey_session_store_io.dart';

const _sessionSchema = 'flywheel.desktop-journey-session/v1';
const journeyLocalMaxBytes = 1048576;
const _maxDepth = 16;
const _maxNodes = 4096;
final _journeyRef = RegExp(r'^jrn_[0-9a-f]{32}$');
final _selectionRef = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$');

enum JourneyLocalFailure {
  invalidRecord,
  corruptStore,
  writeFailed,
  notFound,
  acknowledgementMismatch,
}

class JourneyLocalStoreException implements Exception {
  const JourneyLocalStoreException(this.failure);
  final JourneyLocalFailure failure;

  @override
  String toString() => 'Journey local store failure: ${failure.name}';
}

typedef JourneyBeforeRename = void Function(File temporary);
typedef JourneyRenameFile = void Function(File temporary, String targetPath);
typedef JourneyTemporaryFile = File Function(File target);
var _temporarySequence = 0;

class JourneySession {
  factory JourneySession({
    required String journeyRef,
    required JourneyLens lens,
    String? selectionRef,
    String? operationRef,
    String? operationEventHeadSha256,
    String? operationRequestSha256,
    bool detailsExpanded = false,
    bool recoveryVisible = false,
  }) {
    _valid(_journeyRef.hasMatch(journeyRef));
    _valid(lens != JourneyLens.invalidResponse);
    _valid(selectionRef == null || _selectionRef.hasMatch(selectionRef));
    _valid(operationRef == null || operationRefPattern.hasMatch(operationRef));
    _valid(
      operationEventHeadSha256 == null ||
          sha256Pattern.hasMatch(operationEventHeadSha256),
    );
    _valid((operationRef == null) == (operationEventHeadSha256 == null));
    _valid(
      operationRequestSha256 == null ||
          sha256Pattern.hasMatch(operationRequestSha256),
    );
    return JourneySession._(
      journeyRef,
      lens,
      selectionRef,
      operationRef,
      operationEventHeadSha256,
      operationRequestSha256,
      detailsExpanded,
      recoveryVisible,
    );
  }

  const JourneySession._(
    this.journeyRef,
    this.lens,
    this.selectionRef,
    this.operationRef,
    this.operationEventHeadSha256,
    this.operationRequestSha256,
    this.detailsExpanded,
    this.recoveryVisible,
  );
  final String journeyRef;
  final JourneyLens lens;
  final String? selectionRef;
  final String? operationRef;
  final String? operationEventHeadSha256;
  final String? operationRequestSha256;
  final bool detailsExpanded;
  final bool recoveryVisible;
}

class JourneySessionStore {
  JourneySessionStore({
    File? file,
    this.beforeRename,
    this.renameFile,
    this.temporaryFile,
  }) : storageFile = file ??
            File(
              '${flywheelHome()}${Platform.pathSeparator}journey-session.json',
            );

  final File storageFile;
  final JourneyBeforeRename? beforeRename;
  final JourneyRenameFile? renameFile;
  final JourneyTemporaryFile? temporaryFile;

  JourneySession? load() {
    if (!storageFile.existsSync()) return null;
    try {
      final value = readJourneyLocalObject(storageFile);
      final expected = <String>{
        'schema',
        'journey_ref',
        'lens',
        'details_expanded',
        'recovery_visible',
        if (value.containsKey('selection_ref')) 'selection_ref',
        if (value.containsKey('operation_ref')) 'operation_ref',
        if (value.containsKey('operation_event_head_sha256'))
          'operation_event_head_sha256',
        if (value.containsKey('operation_request_sha256'))
          'operation_request_sha256',
      };
      _valid(value.keys.toSet().containsAll(expected));
      _valid(
        value.length == expected.length && value['schema'] == _sessionSchema,
      );
      _valid(value['journey_ref'] is String && value['lens'] is String);
      _valid(
        value['details_expanded'] is bool && value['recovery_visible'] is bool,
      );
      _valid(
        !value.containsKey('selection_ref') || value['selection_ref'] is String,
      );
      _valid(
        !value.containsKey('operation_ref') || value['operation_ref'] is String,
      );
      _valid(
        !value.containsKey('operation_event_head_sha256') ||
            value['operation_event_head_sha256'] is String,
      );
      _valid(
        !value.containsKey('operation_request_sha256') ||
            value['operation_request_sha256'] is String,
      );
      return JourneySession(
        journeyRef: value['journey_ref'] as String,
        lens: _parseLens(value['lens']),
        selectionRef: value['selection_ref'] as String?,
        operationRef: value['operation_ref'] as String?,
        operationEventHeadSha256:
            value['operation_event_head_sha256'] as String?,
        operationRequestSha256: value['operation_request_sha256'] as String?,
        detailsExpanded: value['details_expanded'] as bool,
        recoveryVisible: value['recovery_visible'] as bool,
      );
    } catch (_) {
      throw const JourneyLocalStoreException(JourneyLocalFailure.corruptStore);
    }
  }

  void save(JourneySession session) {
    final value = <String, dynamic>{
      'details_expanded': session.detailsExpanded,
      'journey_ref': session.journeyRef,
      'lens': _lensWire(session.lens),
      if (session.operationRef != null) 'operation_ref': session.operationRef,
      if (session.operationEventHeadSha256 != null)
        'operation_event_head_sha256': session.operationEventHeadSha256,
      if (session.operationRequestSha256 != null)
        'operation_request_sha256': session.operationRequestSha256,
      'recovery_visible': session.recoveryVisible,
      'schema': _sessionSchema,
      if (session.selectionRef != null) 'selection_ref': session.selectionRef,
    };
    writeJourneyLocalObject(
      storageFile,
      value,
      beforeRename: beforeRename,
      renameFile: renameFile,
      temporaryFile: temporaryFile,
    );
  }

  void clear() {
    try {
      if (storageFile.existsSync()) storageFile.deleteSync();
    } catch (_) {
      throw const JourneyLocalStoreException(JourneyLocalFailure.writeFailed);
    }
  }
}

JourneyLens _parseLens(Object? raw) => switch (raw) {
      'Rescue' => JourneyLens.rescue,
      'Diagnose' => JourneyLens.diagnose,
      'Verify' => JourneyLens.verify,
      _ => throw const JourneyLocalStoreException(
          JourneyLocalFailure.invalidRecord,
        ),
    };

String _lensWire(JourneyLens lens) => switch (lens) {
      JourneyLens.rescue => 'Rescue',
      JourneyLens.diagnose => 'Diagnose',
      JourneyLens.verify => 'Verify',
      JourneyLens.invalidResponse => throw const JourneyLocalStoreException(
          JourneyLocalFailure.invalidRecord,
        ),
    };

String journeyLocalDefaultPath(String name) =>
    '${flywheelHome()}${Platform.pathSeparator}$name';

void _valid(bool condition) {
  if (!condition) {
    throw const JourneyLocalStoreException(JourneyLocalFailure.invalidRecord);
  }
}
