import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

typedef DraftBytesValidator = bool Function(List<int> bytes, String pathKey);
typedef DraftTemporaryFile = File Function(File target);
typedef DraftBeforeRename = void Function(File temporary);
typedef DraftRename = void Function(File temporary, String targetPath);
typedef DraftDelete = void Function(File target);

final class DraftTransactionException implements Exception {
  const DraftTransactionException(this.busy);
  final bool busy;
}

final class CodeDraftTransaction {
  CodeDraftTransaction({required this.root, required this.workspaceRef});

  final Directory root;
  final String workspaceRef;
  static final _target = RegExp(r'^([0-9a-f]{64})\.json$');
  static final _owned =
      RegExp(r'^([0-9a-f]{64})\.json\.fw-(write|delete)\.([0-9]+)\.'
          r'([0-9a-f]{32})\.([0-9a-f]{64})\.tmp$');

  Directory get directory => Directory('${root.path}/$workspaceRef');

  void validateTarget(File target) {
    var current = root.absolute;
    while (true) {
      _regularOrMissing(current.path, allowDirectory: true);
      final parent = current.parent;
      if (parent.path == current.path) break;
      current = parent;
    }
    if (target.parent.existsSync()) {
      _regularOrMissing(target.parent.path, allowDirectory: true);
    }
    _regularOrMissing(target.path);
  }

  void recover(DraftBytesValidator valid) {
    if (!directory.existsSync()) return;
    final groups = _admit();
    for (final key in groups.keys.toList()..sort()) {
      locked(key, () => _recoverGroup(key, groups[key]!, valid));
    }
  }

  T locked<T>(String key, T Function() action) {
    final locks = Directory('${root.path}/.locks')..createSync(recursive: true);
    final file = File('${locks.path}/$workspaceRef.$key.lock');
    final handle = file.openSync(mode: FileMode.append);
    try {
      if (handle.lengthSync() == 0) {
        handle.writeByteSync(0);
      }
      try {
        handle.lockSync(FileLock.exclusive, 0, 1);
      } catch (_) {
        throw const DraftTransactionException(true);
      }
      try {
        return action();
      } finally {
        handle.unlockSync(0, 1);
      }
    } finally {
      handle.closeSync();
    }
  }

  String write(
    File target,
    List<int> bytes, {
    required DraftBytesValidator valid,
    DraftTemporaryFile? temporaryFile,
    DraftBeforeRename? beforeRename,
    DraftRename? renameFile,
  }) {
    final recordSha = sha256.convert(bytes).toString();
    final pathKey = target.uri.pathSegments.last.substring(0, 64);
    final prior = target.existsSync() ? target.readAsBytesSync() : null;
    final temporary = temporaryFile?.call(target) ??
        File('${target.path}.fw-write.$pid.${_nonce()}.$recordSha.tmp');
    if (_entryExists(temporary.path)) {
      throw const DraftTransactionException(false);
    }
    try {
      temporary.parent.createSync(recursive: true);
      temporary.writeAsBytesSync(bytes, flush: true);
      if (!_same(temporary.readAsBytesSync(), bytes)) {
        throw const DraftTransactionException(false);
      }
      beforeRename?.call(temporary);
      (renameFile ?? (file, path) => file.renameSync(path))(
          temporary, target.path);
      if (!target.existsSync() || !_same(target.readAsBytesSync(), bytes)) {
        throw const DraftTransactionException(false);
      }
      return recordSha;
    } catch (_) {
      _cleanup(temporary);
      _rollback(target, prior, recordSha, pathKey, valid);
      rethrow;
    }
  }

  bool delete(
    File target, {
    required String expectedRecordSha256,
    required bool Function(List<int>) matches,
    DraftDelete? deleteFile,
  }) {
    if (!target.existsSync()) return false;
    final bytes = target.readAsBytesSync();
    if (sha256.convert(bytes).toString() != expectedRecordSha256 ||
        !matches(bytes)) {
      throw const DraftTransactionException(false);
    }
    final tombstone = File('${target.path}.fw-delete.$pid.${_nonce()}.'
        '$expectedRecordSha256.tmp');
    target.renameSync(tombstone.path);
    try {
      final actual = tombstone.readAsBytesSync();
      if (sha256.convert(actual).toString() != expectedRecordSha256 ||
          !matches(actual)) {
        throw const DraftTransactionException(false);
      }
      (deleteFile ?? (file) => file.deleteSync())(tombstone);
      return true;
    } catch (_) {
      if (!target.existsSync() && tombstone.existsSync()) {
        tombstone.renameSync(target.path);
      } else {
        _quarantine(tombstone);
      }
      rethrow;
    }
  }

  Map<String, List<File>> _admit() {
    final groups = <String, List<File>>{};
    for (final entity in directory.listSync(followLinks: false)) {
      if (entity is! File ||
          FileSystemEntity.typeSync(entity.path, followLinks: false) !=
              FileSystemEntityType.file) {
        throw const DraftTransactionException(false);
      }
      final name = entity.uri.pathSegments.last;
      final target = _target.firstMatch(name);
      final owned = _owned.firstMatch(name);
      if (target == null && owned == null) {
        throw const DraftTransactionException(false);
      }
      final key = (target ?? owned)!.group(1)!;
      (groups[key] ??= []).add(entity);
    }
    return groups;
  }

  void _recoverGroup(
      String key, List<File> entries, DraftBytesValidator valid) {
    final target = File('${directory.path}/$key.json');
    final owned = entries
        .where((file) => file.uri.pathSegments.last != '$key.json')
        .toList();
    if (target.existsSync()) {
      for (final file in owned) {
        _quarantine(file);
      }
      return;
    }
    final writes = <File>[];
    final deletes = <File>[];
    for (final file in owned) {
      final match = _owned.firstMatch(file.uri.pathSegments.last)!;
      final bytes = file.readAsBytesSync();
      final complete = sha256.convert(bytes).toString() == match.group(5) &&
          valid(bytes, key);
      if (!complete) {
        _quarantine(file);
      } else if (match.group(2) == 'write') {
        writes.add(file);
      } else {
        deletes.add(file);
      }
    }
    if (writes.length + deletes.length > 1 ||
        (writes.isNotEmpty && deletes.isNotEmpty)) {
      throw const DraftTransactionException(false);
    }
    final candidate = writes.isNotEmpty
        ? writes.single
        : deletes.isNotEmpty
            ? deletes.single
            : null;
    candidate?.renameSync(target.path);
  }

  void _rollback(File target, List<int>? prior, String attempted,
      String pathKey, DraftBytesValidator valid) {
    if (!target.existsSync()) {
      if (prior != null) target.writeAsBytesSync(prior, flush: true);
      return;
    }
    final current = target.readAsBytesSync();
    final digest = sha256.convert(current).toString();
    if (digest != attempted && valid(current, pathKey)) return;
    if (prior == null) {
      target.deleteSync();
    } else {
      target.writeAsBytesSync(prior, flush: true);
    }
  }

  void _quarantine(File file) {
    if (!file.existsSync()) return;
    final bytes = file.readAsBytesSync();
    final digest = sha256.convert(bytes).toString();
    final quarantine = Directory('${root.path}/.quarantine')
      ..createSync(recursive: true);
    final name =
        sha256.convert(utf8.encode('$workspaceRef:${file.path}')).toString();
    final target = File('${quarantine.path}/$name.$digest');
    if (target.existsSync()) {
      file.deleteSync();
    } else {
      file.renameSync(target.path);
    }
  }

  void _cleanup(File file) {
    if (_entryExists(file.path) && file.existsSync()) {
      file.deleteSync();
    }
  }

  bool _entryExists(String path) =>
      FileSystemEntity.typeSync(path, followLinks: false) !=
      FileSystemEntityType.notFound;
  String _nonce() => DateTime.now()
      .microsecondsSinceEpoch
      .toRadixString(16)
      .padLeft(32, '0')
      .substring(0, 32);

  void _regularOrMissing(String path, {bool allowDirectory = false}) {
    final type = FileSystemEntity.typeSync(path, followLinks: false);
    final accepted = type == FileSystemEntityType.notFound ||
        type == FileSystemEntityType.file ||
        (allowDirectory && type == FileSystemEntityType.directory);
    if (!accepted) {
      throw const DraftTransactionException(false);
    }
  }
}

Map<String, dynamic> decodeBoundedCanonicalJson(List<int> bytes) {
  if (bytes.length > 1048576) throw const FormatException();
  final text = utf8.decode(bytes);
  final value = jsonDecode(text);
  if (value is! Map<String, dynamic> || jsonEncode(value) != text) {
    throw const FormatException();
  }
  _guardJson(value, 0, [0]);
  return value;
}

void _guardJson(Object? value, int depth, List<int> nodes) {
  if (depth > 16 || ++nodes[0] > 4096) throw const FormatException();
  if (value is Map) {
    for (final entry in value.entries) {
      _guardJson(entry.key, depth + 1, nodes);
      _guardJson(entry.value, depth + 1, nodes);
    }
  } else if (value is List) {
    for (final item in value) {
      _guardJson(item, depth + 1, nodes);
    }
  }
}

bool _same(List<int> left, List<int> right) {
  if (left.length != right.length) return false;
  for (var i = 0; i < left.length; i++) {
    if (left[i] != right[i]) return false;
  }
  return true;
}
