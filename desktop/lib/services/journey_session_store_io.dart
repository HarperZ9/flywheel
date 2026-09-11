part of 'journey_session_store.dart';

Map<String, dynamic> snapshotJourneyLocalJson(
  Map<Object?, Object?> source, {
  required bool Function(String) safeText,
  required bool Function(String) secretKey,
  required bool Function(String) safeRef,
}) {
  final result = _JsonGuard(safeText, secretKey, safeRef).object(source);
  _valid(canonicalJourneyLocalBytes(result).length <= journeyLocalMaxBytes);
  return result;
}

class _JsonGuard {
  _JsonGuard([this.safeText, this.secretKey, this.safeRef]);
  final bool Function(String)? safeText;
  final bool Function(String)? secretKey;
  final bool Function(String)? safeRef;
  var nodes = 0;

  Map<String, dynamic> object(Object? source) {
    final result = _visit(source, 0, null);
    _valid(result is Map<String, dynamic>);
    return result as Map<String, dynamic>;
  }

  dynamic _visit(Object? value, int depth, String? key) {
    _valid(depth <= _maxDepth && ++nodes <= _maxNodes);
    if (value == null || value is bool) return value;
    if (value is num) {
      _valid(value.isFinite);
      return value;
    }
    if (value is String) {
      _valid(safeText?.call(value) ?? true);
      if (key != null && _refKey(key)) _valid(safeRef?.call(value) ?? true);
      return value;
    }
    if (value is List) {
      return List.unmodifiable(
        value.map((item) => _visit(item, depth + 1, key)),
      );
    }
    _valid(value is Map);
    final sorted = SplayTreeMap<String, dynamic>();
    for (final entry in (value as Map).entries) {
      _valid(entry.key is String);
      final name = entry.key as String;
      _valid(
        (safeText?.call(name) ?? true) && !(secretKey?.call(name) ?? false),
      );
      sorted[name] = _visit(entry.value, depth + 1, name);
    }
    return Map<String, dynamic>.unmodifiable(sorted);
  }
}

bool _refKey(String key) =>
    key == 'ref' || key.endsWith('_ref') || key.endsWith('_refs');

List<int> canonicalJourneyLocalBytes(Object? value) =>
    utf8.encode(jsonEncode(value));
String journeyLocalSha256(Object? value) =>
    sha256.convert(canonicalJourneyLocalBytes(value)).toString();

Map<String, dynamic> readJourneyLocalObject(File file) {
  _valid(file.lengthSync() <= journeyLocalMaxBytes);
  final bytes = file.readAsBytesSync();
  _valid(bytes.length <= journeyLocalMaxBytes);
  final decoded = jsonDecode(utf8.decode(bytes));
  final guarded = _JsonGuard().object(decoded);
  _valid(_sameBytes(bytes, canonicalJourneyLocalBytes(guarded)));
  return guarded;
}

void writeJourneyLocalObject(
  File target,
  Object value, {
  JourneyBeforeRename? beforeRename,
  JourneyRenameFile? renameFile,
  JourneyTemporaryFile? temporaryFile,
}) {
  final bytes = canonicalJourneyLocalBytes(_JsonGuard().object(value));
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
      temporary,
      target.path,
    );
    if (temporary.existsSync() ||
        !target.existsSync() ||
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

bool _sameBytes(List<int> left, List<int> right) {
  if (left.length != right.length) return false;
  for (var index = 0; index < left.length; index++) {
    if (left[index] != right[index]) return false;
  }
  return true;
}

File _uniqueTemporary(File target) => File(
      '${target.path}.$pid.${DateTime.now().microsecondsSinceEpoch}.${_temporarySequence++}.tmp',
    );
