import 'dart:collection';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

import '../client/gateway_auth.dart';
import '../models/evidence_state.dart';

const _sessionSchema = 'flywheel.desktop-journey-session/v1';
const journeyLocalMaxBytes = 1048576;
const _maxDepth = 16;
const _maxNodes = 4096;
final _journeyRef = RegExp(r'^jrn_[0-9a-f]{32}$');
final _selectionRef = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$');
final _windowsPath = RegExp(r'[A-Za-z]:[\\/]');
final _uncPath = RegExp(r'(?:\\\\|//)[^\\/\s]+[\\/][^\s]+');
final _privatePath = RegExp(r'(?:^|[\s=(\[{,:;])/(?!/)[^\s]+|/'
    r'(?:Users|home|private|tmp|var|etc|root|opt|mnt|srv|usr|bin|sbin|lib|'
    r'Applications|Volumes|dev|proc|sys|run)(?:/|$)');
final _fileUri = RegExp(r'(?<![A-Za-z0-9+.-])file:', caseSensitive: false);
final _secretValue = RegExp(
    r'(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bsk-(?:live|proj|ant)[A-Za-z0-9_-]{10,}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b)');
final _assignedSecret = RegExp(
    r'\b(?:secret|password|passwd|api_key|access_key|token|credential)\s*[:=]\s*["\x27]?[A-Za-z0-9/+_-]{12,}',
    caseSensitive: false);
final _secretKeyName = RegExp(r'^(?:api_key|access_token|refresh_token|token|'
    r'password|secret|credential|credentials|private_key|authorization|cookie|'
    r'environment|env|passwd|access_key|.+_(?:api_key|private_key|password|'
    r'secret|credential|token))$');

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
    bool detailsExpanded = false,
    bool recoveryVisible = false,
  }) {
    _valid(_journeyRef.hasMatch(journeyRef));
    _valid(lens != JourneyLens.invalidResponse);
    _valid(selectionRef == null || _selectionRef.hasMatch(selectionRef));
    if (selectionRef != null) {
      snapshotJourneyLocalJson({'selection_ref': selectionRef});
    }
    return JourneySession._(
        journeyRef, lens, selectionRef, detailsExpanded, recoveryVisible);
  }

  const JourneySession._(this.journeyRef, this.lens, this.selectionRef,
      this.detailsExpanded, this.recoveryVisible);
  final String journeyRef;
  final JourneyLens lens;
  final String? selectionRef;
  final bool detailsExpanded;
  final bool recoveryVisible;
}

class JourneySessionStore {
  JourneySessionStore(
      {File? file, this.beforeRename, this.renameFile, this.temporaryFile})
      : storageFile = file ??
            File(
                '${flywheelHome()}${Platform.pathSeparator}journey-session.json');

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
      };
      _valid(value.keys.toSet().containsAll(expected));
      _valid(
          value.length == expected.length && value['schema'] == _sessionSchema);
      _valid(value['journey_ref'] is String && value['lens'] is String);
      _valid(value['details_expanded'] is bool &&
          value['recovery_visible'] is bool);
      _valid(!value.containsKey('selection_ref') ||
          value['selection_ref'] is String);
      return JourneySession(
        journeyRef: value['journey_ref'] as String,
        lens: _parseLens(value['lens']),
        selectionRef: value['selection_ref'] as String?,
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
      'recovery_visible': session.recoveryVisible,
      'schema': _sessionSchema,
      if (session.selectionRef != null) 'selection_ref': session.selectionRef,
    };
    writeJourneyLocalObject(storageFile, value,
        beforeRename: beforeRename,
        renameFile: renameFile,
        temporaryFile: temporaryFile);
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
          JourneyLocalFailure.invalidRecord),
    };

String _lensWire(JourneyLens lens) => switch (lens) {
      JourneyLens.rescue => 'Rescue',
      JourneyLens.diagnose => 'Diagnose',
      JourneyLens.verify => 'Verify',
      JourneyLens.invalidResponse => throw const JourneyLocalStoreException(
          JourneyLocalFailure.invalidRecord),
    };

Map<String, dynamic> snapshotJourneyLocalJson(Map<Object?, Object?> source) {
  var nodes = 0;
  dynamic visit(Object? value, int depth, String? key) {
    _valid(depth <= _maxDepth && ++nodes <= _maxNodes);
    if (value == null || value is bool) return value;
    if (value is num) {
      _valid(value.isFinite);
      return value;
    }
    if (value is String) {
      _valid(isSafeJourneyLocalText(value));
      if (key != null &&
          (key == 'ref' || key.endsWith('_ref') || key.endsWith('_refs'))) {
        _valid(_safeRef(value));
      }
      return value;
    }
    if (value is List) {
      return List.unmodifiable(
          value.map((item) => visit(item, depth + 1, key)));
    }
    if (value is Map) {
      final sorted = SplayTreeMap<String, dynamic>();
      for (final entry in value.entries) {
        _valid(entry.key is String);
        final name = entry.key as String;
        _valid(isSafeJourneyLocalText(name) && !_secretKey(name));
        sorted[name] = visit(entry.value, depth + 1, name);
      }
      return Map<String, dynamic>.unmodifiable(sorted);
    }
    throw const JourneyLocalStoreException(JourneyLocalFailure.invalidRecord);
  }

  final result = visit(source, 0, null) as Map<String, dynamic>;
  _valid(canonicalJourneyLocalBytes(result).length <= journeyLocalMaxBytes);
  return result;
}

List<int> canonicalJourneyLocalBytes(Object? value) =>
    utf8.encode(jsonEncode(value));
String journeyLocalSha256(Object? value) =>
    sha256.convert(canonicalJourneyLocalBytes(value)).toString();

Map<String, dynamic> readJourneyLocalObject(File file) {
  _valid(file.lengthSync() <= journeyLocalMaxBytes);
  final bytes = file.readAsBytesSync();
  _valid(bytes.length <= journeyLocalMaxBytes);
  final decoded = jsonDecode(utf8.decode(bytes));
  _valid(decoded is Map<String, dynamic>);
  return decoded as Map<String, dynamic>;
}

void writeJourneyLocalObject(File target, Object value,
    {JourneyBeforeRename? beforeRename,
    JourneyRenameFile? renameFile,
    JourneyTemporaryFile? temporaryFile}) {
  final bytes = canonicalJourneyLocalBytes(value);
  _valid(bytes.length <= journeyLocalMaxBytes);
  File? temporary;
  RandomAccessFile? handle;
  var ownsTemporary = false;
  try {
    target.parent.createSync(recursive: true);
    temporary = temporaryFile?.call(target) ?? _uniqueTemporary(target);
    temporary.createSync(exclusive: true);
    ownsTemporary = true;
    handle = temporary.openSync(mode: FileMode.writeOnly);
    handle.writeFromSync(bytes);
    handle.flushSync();
    handle.closeSync();
    handle = null;
    beforeRename?.call(temporary);
    (renameFile ?? (file, path) => file.renameSync(path))(
        temporary, target.path);
    if (!target.existsSync() ||
        target.lengthSync() != bytes.length ||
        sha256.convert(target.readAsBytesSync()).toString() !=
            sha256.convert(bytes).toString()) {
      throw const JourneyLocalStoreException(JourneyLocalFailure.writeFailed);
    }
    temporary = null;
  } on JourneyLocalStoreException {
    rethrow;
  } catch (_) {
    throw const JourneyLocalStoreException(JourneyLocalFailure.writeFailed);
  } finally {
    handle?.closeSync();
    if (ownsTemporary && (temporary?.existsSync() ?? false)) {
      temporary!.deleteSync();
    }
  }
}

File _uniqueTemporary(File target) => File(
    '${target.path}.$pid.${DateTime.now().microsecondsSinceEpoch}.${_temporarySequence++}.tmp');

String journeyLocalDefaultPath(String name) =>
    '${flywheelHome()}${Platform.pathSeparator}$name';

bool isSafeJourneyLocalText(String value) {
  String decoded;
  try {
    decoded = Uri.decodeFull(value);
  } on FormatException {
    return false;
  }
  return !_windowsPath.hasMatch(value) &&
      !_uncPath.hasMatch(value) &&
      !_privatePath.hasMatch(value) &&
      !_fileUri.hasMatch(decoded) &&
      !_secretValue.hasMatch(value) &&
      !_assignedSecret.hasMatch(value);
}

bool _secretKey(String key) {
  final name = key.toLowerCase().replaceAll('-', '_');
  return _secretKeyName.hasMatch(name);
}

bool _safeRef(String value) =>
    value.isNotEmpty &&
    value.length <= 256 &&
    !value.startsWith('/') &&
    !value.startsWith(r'\') &&
    !value.contains(':') &&
    !value.split(RegExp(r'[\\/]')).contains('..');

void _valid(bool condition) {
  if (!condition) {
    throw const JourneyLocalStoreException(JourneyLocalFailure.invalidRecord);
  }
}
