import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

import 'journey_session_store.dart';

const _schema = 'flywheel.desktop-code-draft/v1';
final _sha256 = RegExp(r'^[0-9a-f]{64}$');

enum CodeDraftFailure {
  invalidRecord,
  corruptStore,
  writeFailed,
  notFound,
  digestMismatch,
}

class CodeDraftStoreException implements Exception {
  const CodeDraftStoreException(this.failure);
  final CodeDraftFailure failure;

  @override
  String toString() => 'Code draft store failure: ${failure.name}';
}

typedef CodeDraftBeforeRename = void Function(File temporary);
typedef CodeDraftRenameFile = void Function(File temporary, String targetPath);
typedef CodeDraftTemporaryFile = File Function(File target);
typedef CodeDraftDeleteFile = void Function(File target);

final class CodeDraft {
  factory CodeDraft({
    required String path,
    required String diskSha256,
    required String bufferSha256,
    required String text,
    required DateTime updatedAt,
  }) {
    final relative = normalizeCodeDraftPath(path);
    _valid(_sha256.hasMatch(diskSha256));
    _valid(_sha256.hasMatch(bufferSha256));
    _valid(bufferSha256 == sha256.convert(utf8.encode(text)).toString());
    _valid(updatedAt.isUtc);
    return CodeDraft._(
        relative, diskSha256, bufferSha256, text, updatedAt.toUtc());
  }

  const CodeDraft._(
      this.path, this.diskSha256, this.bufferSha256, this.text, this.updatedAt);
  final String path;
  final String diskSha256;
  final String bufferSha256;
  final String text;
  final DateTime updatedAt;
}

final class CodeDraftStore {
  CodeDraftStore({
    Directory? root,
    this.beforeRename,
    this.renameFile,
    this.temporaryFile,
    this.deleteFile,
  }) : storageRoot = root ?? Directory(journeyLocalDefaultPath('code-drafts'));

  final Directory storageRoot;
  final CodeDraftBeforeRename? beforeRename;
  final CodeDraftRenameFile? renameFile;
  final CodeDraftTemporaryFile? temporaryFile;
  final CodeDraftDeleteFile? deleteFile;

  List<CodeDraft> load({required String workspaceRef}) {
    _workspaceRef(workspaceRef);
    try {
      _safeRoot();
      final directory = Directory('${storageRoot.path}/$workspaceRef');
      if (!directory.existsSync()) return const [];
      _notLink(directory.path);
      final drafts = <CodeDraft>[];
      for (final entity in directory.listSync(followLinks: false)) {
        _valid(entity is File && entity.path.endsWith('.json'));
        final root = readJourneyLocalObject(entity as File);
        _keys(root, const {'draft', 'schema', 'workspace_ref'});
        _valid(
            root['schema'] == _schema && root['workspace_ref'] == workspaceRef);
        final raw = root['draft'];
        _valid(raw is Map<String, dynamic>);
        final draft = _decode(raw as Map<String, dynamic>);
        final expected = '${sha256.convert(utf8.encode(draft.path))}.json';
        _valid(entity.uri.pathSegments.last == expected);
        drafts.add(draft);
      }
      drafts.sort((a, b) => a.path.compareTo(b.path));
      return List.unmodifiable(drafts);
    } catch (error) {
      if (error is CodeDraftStoreException &&
          error.failure == CodeDraftFailure.invalidRecord) {
        throw const CodeDraftStoreException(CodeDraftFailure.corruptStore);
      }
      if (error is CodeDraftStoreException) rethrow;
      throw const CodeDraftStoreException(CodeDraftFailure.corruptStore);
    }
  }

  void save({required String workspaceRef, required CodeDraft draft}) {
    _workspaceRef(workspaceRef);
    late final Map<String, dynamic> value;
    try {
      value = snapshotJourneyLocalJson({
        'draft': _encode(draft),
        'schema': _schema,
        'workspace_ref': workspaceRef,
      }, safeText: (_) => true, secretKey: (_) => false, safeRef: (_) => true);
    } catch (_) {
      throw const CodeDraftStoreException(CodeDraftFailure.invalidRecord);
    }
    final target = _record(workspaceRef, draft.path);
    _safeTarget(target);
    final prior = target.existsSync() ? target.readAsBytesSync() : null;
    try {
      writeJourneyLocalObject(target, value,
          beforeRename: beforeRename,
          renameFile: renameFile,
          temporaryFile: temporaryFile);
    } catch (_) {
      _restore(target, prior);
      throw const CodeDraftStoreException(CodeDraftFailure.writeFailed);
    }
  }

  void delete({
    required String workspaceRef,
    required String path,
    required String expectedBufferSha256,
  }) {
    _workspaceRef(workspaceRef);
    final relative = normalizeCodeDraftPath(path);
    _valid(_sha256.hasMatch(expectedBufferSha256));
    final target = _record(workspaceRef, relative);
    _safeTarget(target);
    if (!target.existsSync()) {
      throw const CodeDraftStoreException(CodeDraftFailure.notFound);
    }
    final matches =
        load(workspaceRef: workspaceRef).where((item) => item.path == relative);
    final draft = matches.isEmpty ? null : matches.single;
    if (draft == null) {
      throw const CodeDraftStoreException(CodeDraftFailure.notFound);
    }
    if (draft.bufferSha256 != expectedBufferSha256) {
      throw const CodeDraftStoreException(CodeDraftFailure.digestMismatch);
    }
    try {
      (deleteFile ?? (file) => file.deleteSync())(target);
    } catch (_) {
      throw const CodeDraftStoreException(CodeDraftFailure.writeFailed);
    }
  }

  File _record(String workspaceRef, String path) {
    final name = sha256.convert(utf8.encode(path)).toString();
    return File('${storageRoot.path}/$workspaceRef/$name.json');
  }

  void _safeTarget(File target) {
    _safeRoot();
    final workspace = target.parent;
    if (workspace.existsSync()) _notLink(workspace.path);
    if (target.existsSync() ||
        FileSystemEntity.typeSync(target.path, followLinks: false) !=
            FileSystemEntityType.notFound) {
      _notLink(target.path);
    }
  }

  void _safeRoot() {
    var current = storageRoot.absolute;
    while (true) {
      if (FileSystemEntity.typeSync(current.path, followLinks: false) ==
          FileSystemEntityType.link) {
        _valid(false);
      }
      final parent = current.parent;
      if (parent.path == current.path) break;
      current = parent;
    }
  }

  void _notLink(String path) =>
      _valid(FileSystemEntity.typeSync(path, followLinks: false) !=
          FileSystemEntityType.link);

  void _restore(File target, List<int>? prior) {
    try {
      if (FileSystemEntity.typeSync(target.path, followLinks: false) ==
          FileSystemEntityType.link) {
        Link(target.path).deleteSync();
      }
      _safeTarget(target);
      if (prior == null) {
        if (target.existsSync()) target.deleteSync();
      } else {
        target.parent.createSync(recursive: true);
        target.writeAsBytesSync(prior, flush: true);
      }
    } catch (_) {
      throw const CodeDraftStoreException(CodeDraftFailure.writeFailed);
    }
  }
}

CodeDraft _decode(Map<String, dynamic> value) {
  _keys(value, const {
    'buffer_sha256',
    'disk_sha256',
    'path',
    'text',
    'updated_at',
  });
  _valid(value['path'] is String && value['text'] is String);
  _valid(value['disk_sha256'] is String && value['buffer_sha256'] is String);
  final updated = DateTime.tryParse(
      value['updated_at'] is String ? value['updated_at'] as String : '');
  _valid(updated != null && updated.isUtc);
  return CodeDraft(
      path: value['path'] as String,
      diskSha256: value['disk_sha256'] as String,
      bufferSha256: value['buffer_sha256'] as String,
      text: value['text'] as String,
      updatedAt: updated!);
}

Map<String, dynamic> _encode(CodeDraft draft) => {
      'buffer_sha256': draft.bufferSha256,
      'disk_sha256': draft.diskSha256,
      'path': draft.path,
      'text': draft.text,
      'updated_at': draft.updatedAt.toIso8601String(),
    };

String normalizeCodeDraftPath(String value) {
  _valid(value.isNotEmpty && value.length <= 1024);
  final decoded = _decodePercent(value);
  for (final form in [value, decoded]) {
    _valid(!form.startsWith('/') && !form.startsWith(r'\'));
    _valid(!form.contains(':'));
    final parts = form.split(RegExp(r'[\\/]'));
    _valid(
        parts.every((part) => part.isNotEmpty && part != '.' && part != '..'));
  }
  return value.replaceAll(r'\', '/');
}

String _decodePercent(String value) {
  try {
    return value.replaceAllMapped(RegExp(r'(?:%[0-9A-Fa-f]{2})+'),
        (match) => Uri.decodeComponent(match.group(0)!));
  } catch (_) {
    throw const CodeDraftStoreException(CodeDraftFailure.invalidRecord);
  }
}

void _workspaceRef(String value) => _valid(_sha256.hasMatch(value));
void _keys(Map<String, dynamic> value, Set<String> expected) =>
    _valid(value.length == expected.length &&
        value.keys.toSet().containsAll(expected));
void _valid(bool condition) {
  if (!condition) {
    throw const CodeDraftStoreException(CodeDraftFailure.invalidRecord);
  }
}
