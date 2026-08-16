import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

import 'code_draft_transaction.dart';
import 'journey_session_store.dart';

const _schema = 'flywheel.desktop-code-draft/v1';
final _sha256 = RegExp(r'^[0-9a-f]{64}$');

enum CodeDraftFailure {
  invalidRecord,
  corruptStore,
  writeFailed,
  notFound,
  digestMismatch,
  storeBusy,
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

enum CodeDraftDeleteResult { deleted, alreadyAbsent }

final class StoredCodeDraft {
  const StoredCodeDraft(this.draft, this.recordSha256);
  final CodeDraft draft;
  final String recordSha256;
}

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

  List<StoredCodeDraft> load({required String workspaceRef}) {
    _workspaceRef(workspaceRef);
    try {
      final transaction = _transaction(workspaceRef)
        ..validateTarget(_record(workspaceRef, 'x'));
      final directory = Directory('${storageRoot.path}/$workspaceRef');
      if (!directory.existsSync()) return const [];
      transaction.recover(
          (bytes, key) => _canDecode(bytes, workspaceRef, pathKey: key));
      final drafts = <StoredCodeDraft>[];
      for (final entity in directory.listSync(followLinks: false)) {
        _valid(entity is File && entity.path.endsWith('.json'));
        final file = entity as File;
        final key = file.uri.pathSegments.last.substring(0, 64);
        drafts.add(transaction.locked(key, () {
          final bytes = file.readAsBytesSync();
          final stored = _decodeRecord(bytes, workspaceRef);
          final expected =
              '${sha256.convert(utf8.encode(stored.draft.path))}.json';
          _valid(file.uri.pathSegments.last == expected);
          return stored;
        }));
      }
      drafts.sort((a, b) => a.draft.path.compareTo(b.draft.path));
      return List.unmodifiable(drafts);
    } catch (error) {
      if (error is DraftTransactionException && error.busy) {
        throw const CodeDraftStoreException(CodeDraftFailure.storeBusy);
      }
      if (error is CodeDraftStoreException &&
          error.failure == CodeDraftFailure.invalidRecord) {
        throw const CodeDraftStoreException(CodeDraftFailure.corruptStore);
      }
      if (error is CodeDraftStoreException) rethrow;
      throw const CodeDraftStoreException(CodeDraftFailure.corruptStore);
    }
  }

  StoredCodeDraft save(
      {required String workspaceRef, required CodeDraft draft}) {
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
    final transaction = _transaction(workspaceRef)..validateTarget(target);
    final bytes = utf8.encode(jsonEncode(value));
    try {
      target.parent.createSync(recursive: true);
      transaction
          .recover((raw, key) => _canDecode(raw, workspaceRef, pathKey: key));
      final key = target.uri.pathSegments.last.substring(0, 64);
      final digest = transaction.locked(
          key,
          () => transaction.write(target, bytes,
              valid: (raw, key) => _canDecode(raw, workspaceRef, pathKey: key),
              beforeRename: beforeRename,
              renameFile: renameFile,
              temporaryFile: temporaryFile));
      return StoredCodeDraft(draft, digest);
    } on DraftTransactionException catch (error) {
      if (error.busy) {
        throw const CodeDraftStoreException(CodeDraftFailure.storeBusy);
      }
      throw const CodeDraftStoreException(CodeDraftFailure.writeFailed);
    } on CodeDraftStoreException {
      rethrow;
    } catch (_) {
      throw const CodeDraftStoreException(CodeDraftFailure.writeFailed);
    }
  }

  CodeDraftDeleteResult delete({
    required String workspaceRef,
    required String path,
    required String expectedBufferSha256,
    required String expectedRecordSha256,
  }) {
    _workspaceRef(workspaceRef);
    final relative = normalizeCodeDraftPath(path);
    _valid(_sha256.hasMatch(expectedBufferSha256));
    _valid(_sha256.hasMatch(expectedRecordSha256));
    final target = _record(workspaceRef, relative);
    final transaction = _transaction(workspaceRef)..validateTarget(target);
    try {
      if (target.parent.existsSync()) {
        transaction
            .recover((raw, key) => _canDecode(raw, workspaceRef, pathKey: key));
      }
      final key = target.uri.pathSegments.last.substring(0, 64);
      final deleted = transaction.locked(
          key,
          () => transaction.delete(target,
                  expectedRecordSha256: expectedRecordSha256, matches: (bytes) {
                final stored = _decodeRecord(bytes, workspaceRef);
                if (stored.draft.path != relative ||
                    stored.draft.bufferSha256 != expectedBufferSha256) {
                  throw const CodeDraftStoreException(
                      CodeDraftFailure.digestMismatch);
                }
                return true;
              }, deleteFile: deleteFile));
      return deleted
          ? CodeDraftDeleteResult.deleted
          : CodeDraftDeleteResult.alreadyAbsent;
    } on CodeDraftStoreException {
      rethrow;
    } on DraftTransactionException catch (error) {
      if (error.busy) {
        throw const CodeDraftStoreException(CodeDraftFailure.storeBusy);
      }
      throw const CodeDraftStoreException(CodeDraftFailure.writeFailed);
    } catch (_) {
      throw const CodeDraftStoreException(CodeDraftFailure.writeFailed);
    }
  }

  CodeDraftTransaction _transaction(String workspaceRef) =>
      CodeDraftTransaction(root: storageRoot, workspaceRef: workspaceRef);

  File _record(String workspaceRef, String path) {
    final name = sha256.convert(utf8.encode(path)).toString();
    return File('${storageRoot.path}/$workspaceRef/$name.json');
  }
}

StoredCodeDraft _decodeRecord(List<int> bytes, String workspaceRef) {
  final root = decodeBoundedCanonicalJson(bytes);
  _keys(root, const {'draft', 'schema', 'workspace_ref'});
  _valid(root['schema'] == _schema && root['workspace_ref'] == workspaceRef);
  _valid(root['draft'] is Map<String, dynamic>);
  final draft = _decode(root['draft'] as Map<String, dynamic>);
  return StoredCodeDraft(draft, sha256.convert(bytes).toString());
}

bool _canDecode(List<int> bytes, String workspaceRef, {String? pathKey}) {
  late final StoredCodeDraft stored;
  try {
    stored = _decodeRecord(bytes, workspaceRef);
  } catch (_) {
    return false;
  }
  if (pathKey != null &&
      sha256.convert(utf8.encode(stored.draft.path)).toString() != pathKey) {
    throw const CodeDraftStoreException(CodeDraftFailure.invalidRecord);
  }
  return true;
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
