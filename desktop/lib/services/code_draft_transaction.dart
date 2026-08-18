import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

import 'code_custody_io.dart';

typedef DraftBytesValidator = bool Function(List<int> bytes, String pathKey);
typedef DraftTemporaryFile = File Function(File target);
typedef DraftBeforeRename = void Function(File temporary);
typedef DraftRename = void Function(File temporary, String targetPath);
typedef DraftDelete = void Function(File target);

final class DraftTransactionException implements Exception {
  const DraftTransactionException(this.busy);
  final bool busy;
}

Never _fail() => throw const DraftTransactionException(false);

final class CodeDraftTransaction {
  CodeDraftTransaction({
    required this.root,
    required this.workspaceRef,
    this.readFile = readCodeCustodyFile,
  });

  final Directory root;
  final String workspaceRef;
  final CodeCustodyReadFile readFile;
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
    final locks = _privateDirectory('.locks');
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
    final prior = _validTarget(target, pathKey, valid);
    final temporary = temporaryFile?.call(target) ??
        File('${target.path}.fw-write.$pid.${_nonce()}.$recordSha.tmp');
    if (_entryExists(temporary.path)) _fail();
    try {
      temporary.parent.createSync(recursive: true);
      temporary.writeAsBytesSync(bytes, flush: true);
      if (!_same(readFile(temporary), bytes)) _fail();
      beforeRename?.call(temporary);
      (renameFile ?? (file, path) => file.renameSync(path))(
          temporary, target.path);
      if (!target.existsSync() || !_same(readFile(target), bytes)) _fail();
      return recordSha;
    } catch (_) {
      if (temporary.existsSync()) temporary.deleteSync();
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
    final bytes = readFile(target);
    final digest = sha256.convert(bytes).toString();
    if (digest != expectedRecordSha256 || !matches(bytes)) _fail();
    final tombstone = File('${target.path}.fw-delete.$pid.${_nonce()}.'
        '$expectedRecordSha256.tmp');
    target.renameSync(tombstone.path);
    try {
      final actual = readFile(tombstone);
      final digest = sha256.convert(actual).toString();
      if (digest != expectedRecordSha256 || !matches(actual)) _fail();
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
      final type = FileSystemEntity.typeSync(entity.path, followLinks: false);
      if (entity is! File || type != FileSystemEntityType.file) _fail();
      final name = entity.uri.pathSegments.last;
      final target = _target.firstMatch(name);
      final owned = _owned.firstMatch(name);
      if (target == null && owned == null) _fail();
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
      _validTarget(target, key, valid);
      for (final file in owned) {
        _quarantine(file);
      }
      return;
    }
    final writes = <File>[];
    final deletes = <File>[];
    for (final file in owned) {
      final match = _owned.firstMatch(file.uri.pathSegments.last)!;
      final bytes = readFile(file);
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
      _fail();
    }
    final candidate = writes.isNotEmpty ? writes.single : deletes.firstOrNull;
    candidate?.renameSync(target.path);
  }

  void _rollback(File target, List<int>? prior, String attempted,
      String pathKey, DraftBytesValidator valid) {
    if (FileSystemEntity.typeSync(target.path, followLinks: false) ==
        FileSystemEntityType.link) {
      Link(target.path).deleteSync();
    }
    if (!target.existsSync()) {
      if (prior != null) _restore(target, prior);
      return;
    }
    final current = readFile(target);
    if (sha256.convert(current).toString() != attempted &&
        valid(current, pathKey)) {
      return;
    }
    if (prior == null) target.deleteSync();
    if (prior != null) _restore(target, prior);
  }

  void _restore(File target, List<int> prior) {
    final digest = sha256.convert(prior).toString();
    final temp = File('${target.path}.fw-write.$pid.${_nonce()}.$digest.tmp');
    if (_entryExists(temp.path)) _fail();
    try {
      temp.writeAsBytesSync(prior, flush: true);
      if (!_same(readFile(temp), prior)) _fail();
      temp.renameSync(target.path);
    } catch (_) {
      if (_entryExists(temp.path)) temp.deleteSync();
      rethrow;
    }
  }

  void _quarantine(File file) {
    if (!file.existsSync()) return;
    final bytes = readFile(file);
    final digest = sha256.convert(bytes).toString();
    final quarantine = _privateDirectory('.quarantine');
    final name =
        sha256.convert(utf8.encode('$workspaceRef:${file.path}')).toString();
    final target = File('${quarantine.path}/$name.$digest');
    if (target.existsSync()) {
      file.deleteSync();
    } else {
      file.renameSync(target.path);
    }
  }

  bool _entryExists(String path) =>
      FileSystemEntity.typeSync(path, followLinks: false) !=
      FileSystemEntityType.notFound;

  List<int>? _validTarget(File target, String key, DraftBytesValidator valid) {
    if (!target.existsSync()) return null;
    final bytes = readFile(target);
    if (!valid(bytes, key)) _fail();
    return bytes;
  }

  Directory _privateDirectory(String name) {
    final directory = Directory('${root.path}/$name');
    _regularOrMissing(directory.path, allowDirectory: true);
    directory.createSync(recursive: true);
    _regularOrMissing(directory.path, allowDirectory: true);
    return directory;
  }

  String _nonce() =>
      DateTime.now().microsecondsSinceEpoch.toRadixString(16).padLeft(32, '0');

  void _regularOrMissing(String path, {bool allowDirectory = false}) {
    final type = FileSystemEntity.typeSync(path, followLinks: false);
    final accepted = type == FileSystemEntityType.notFound ||
        type == FileSystemEntityType.file ||
        allowDirectory && type == FileSystemEntityType.directory;
    if (!accepted) _fail();
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

bool _same(List<int> left, List<int> right) =>
    left.length == right.length &&
    left.asMap().entries.every((entry) => right[entry.key] == entry.value);
