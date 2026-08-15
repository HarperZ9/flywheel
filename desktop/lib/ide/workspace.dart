import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

import '../services/code_draft_store.dart';
import 'diff.dart';
import 'highlighter.dart';

const _ignoredDirs = [
  '.git',
  'node_modules',
  'build',
  '.dart_tool',
  '__pycache__',
  'dist',
  '.idea',
  '.vscode',
  '.venv',
  'venv',
  'target',
  '.next'
];
const int editableLimitBytes = 200 * 1024;

class WorkspaceEntry {
  final String path;
  final String name;
  final bool isDir;
  const WorkspaceEntry(
      {required this.path, required this.name, required this.isDir});
}

List<WorkspaceEntry> listDir(String path) {
  final entries = <WorkspaceEntry>[];
  for (final e in Directory(path).listSync(followLinks: false)) {
    final name =
        e.uri.pathSegments.lastWhere((s) => s.isNotEmpty, orElse: () => e.path);
    final isDir = e is Directory;
    if (isDir && _ignoredDirs.contains(name)) continue;
    if (!isDir && name.endsWith('.lock')) continue;
    entries.add(WorkspaceEntry(path: e.path, name: name, isDir: isDir));
  }
  entries.sort((a, b) {
    if (a.isDir != b.isDir) return a.isDir ? -1 : 1;
    return a.name.toLowerCase().compareTo(b.name.toLowerCase());
  });
  return entries;
}

class LoadedFile {
  final String content;
  final String sha256;
  final bool readOnly;
  final String? note;
  const LoadedFile(this.content, this.sha256,
      {this.readOnly = false, this.note});
}

class SavedFile {
  final String sha256;
  const SavedFile(this.sha256);
}

enum DraftDiskState { buffer, baseline, changed, missing }

class DraftDiskView {
  const DraftDiskView(this.state, this.path, this.disk);
  final DraftDiskState state;
  final String path;
  final LoadedFile? disk;
}

class OpenedWorkspaceFile {
  const OpenedWorkspaceFile(this.path, this.relativePath, this.loaded);
  final String path;
  final String relativePath;
  final LoadedFile loaded;
}

class OpenFile {
  OpenFile({
    required this.path,
    required this.relativePath,
    required this.controller,
    required this.diskSha256,
    this.readOnly = false,
    this.note,
    this.dirty = false,
  });
  final String path;
  final String relativePath;
  final CodeEditingController controller;
  String diskSha256;
  bool readOnly;
  String? note;
  bool dirty;
  String get name => relativePath.split('/').last;
}

enum CodeRecoveryKind { restored, alreadySaved, diskChanged, fileMissing }

enum CodeSessionFailure { invalidPath, localStore, readFailed, writeFailed }

class CodeSessionException implements Exception {
  const CodeSessionException(this.failure);
  final CodeSessionFailure failure;
  @override
  String toString() => 'Code session failure: ${failure.name}';
}

class CodeRecoveryConflict {
  const CodeRecoveryConflict(
      this.kind, this.path, this.draft, this.diskText, this.diskSha256);
  final CodeRecoveryKind kind;
  final String path;
  final CodeDraft draft;
  final String? diskText;
  final String? diskSha256;
}

class WorkspaceSessionIo {
  factory WorkspaceSessionIo.open(String root) {
    final canonical = canonicalWorkspaceRoot(root);
    return WorkspaceSessionIo._(canonical, workspaceReference(canonical));
  }

  const WorkspaceSessionIo._(this.root, this.workspaceRef);
  final String root;
  final String workspaceRef;

  OpenedWorkspaceFile openFile(String path) {
    return openWith(path, loadFile);
  }

  OpenedWorkspaceFile openWith(
      String path, LoadedFile Function(String) loader) {
    final admitted = containedFile(root, path);
    return OpenedWorkspaceFile(
        admitted, relativeFile(root, admitted), loader(admitted));
  }

  OpenedWorkspaceFile source(String path, LoadedFile loaded) =>
      OpenedWorkspaceFile(path, relativeFile(root, path), loaded);

  OpenedWorkspaceFile missing(String path, CodeDraft draft) => source(path,
      LoadedFile('', draft.diskSha256, readOnly: true, note: 'file missing'));

  DraftDiskView inspect(CodeDraft draft) {
    final path = absoluteFile(root, draft.path);
    if (!File(path).existsSync()) {
      return DraftDiskView(DraftDiskState.missing, path, null);
    }
    final opened = openFile(path);
    final state = opened.loaded.sha256 == draft.bufferSha256
        ? DraftDiskState.buffer
        : opened.loaded.sha256 == draft.diskSha256
            ? DraftDiskState.baseline
            : DraftDiskState.changed;
    return DraftDiskView(state, opened.path, opened.loaded);
  }

  bool samePath(String left, String right) {
    String normalized(String value) =>
        File(value).absolute.path.replaceAll('/', Platform.pathSeparator);
    final first = normalized(left), second = normalized(right);
    return Platform.isWindows
        ? first.toLowerCase() == second.toLowerCase()
        : first == second;
  }

  int addLoaded(List<OpenFile> open, OpenedWorkspaceFile source,
      {String? text, bool dirty = false, bool? readOnly}) {
    final existing = open.indexWhere((file) => file.path == source.path);
    if (existing >= 0) return existing;
    final loaded = source.loaded;
    open.add(OpenFile(
        path: source.path,
        relativePath: normalizeCodeDraftPath(source.relativePath),
        controller: CodeEditingController(
            text: text ?? loaded.content, language: languageFor(source.path)),
        diskSha256: loaded.sha256,
        readOnly: readOnly ?? loaded.readOnly,
        note: loaded.note,
        dirty: dirty));
    return open.length - 1;
  }

  List<String> dirtyPaths(List<OpenFile> open) => List.unmodifiable((open
      .where((file) => file.dirty)
      .map((file) => file.relativePath)
      .toList()
    ..sort()));

  void snapshot(List<OpenFile> open, Map<String, String> target) {
    target
      ..clear()
      ..addEntries(
          open.map((file) => MapEntry(file.path, file.controller.text)));
  }

  List<FileDiff> reloadClean(List<OpenFile> open, Map<String, String> before,
      LoadedFile Function(String) loader) {
    final values = <FileDiff>[];
    for (final file in open.where((item) => !item.dirty && !item.readOnly)) {
      final fresh = openWith(file.path, loader).loaded;
      if (fresh.content == file.controller.text) continue;
      final prior = before[file.path];
      if (prior != null) {
        values.add(diffFiles(file.relativePath, prior, fresh.content));
      }
      file.controller.text = fresh.content;
      file.diskSha256 = fresh.sha256;
    }
    return List.unmodifiable(values);
  }
}

LoadedFile loadFile(String path) {
  final f = File(path);
  try {
    final bytes = f.readAsBytesSync();
    final digest = sha256.convert(bytes).toString();
    if (bytes.length > editableLimitBytes) {
      final head = String.fromCharCodes(bytes.take(editableLimitBytes));
      return LoadedFile(head, digest,
          readOnly: true,
          note:
              'large file: showing the first ${editableLimitBytes ~/ 1024} KB read-only');
    }
    try {
      return LoadedFile(utf8.decode(bytes), digest);
    } on FormatException {
      return LoadedFile('', digest,
          readOnly: true, note: 'binary file: not editable here');
    }
  } on FileSystemException catch (e) {
    return LoadedFile('', sha256.convert(const <int>[]).toString(),
        readOnly: true, note: 'unreadable: ${e.message}');
  }
}

SavedFile saveFile(String path, String content) {
  final expected = utf8.encode(content);
  final handle = File(path).openSync(mode: FileMode.writeOnly);
  try {
    handle.writeFromSync(expected);
    handle.flushSync();
  } finally {
    handle.closeSync();
  }
  final actual = File(path).readAsBytesSync();
  if (!_sameBytes(expected, actual)) {
    throw const FileSystemException('readback');
  }
  return SavedFile(sha256.convert(actual).toString());
}

String canonicalWorkspaceRoot(String path) =>
    Directory(path).resolveSymbolicLinksSync();

String workspaceReference(String canonicalRoot) {
  final identity =
      Platform.isWindows ? canonicalRoot.toLowerCase() : canonicalRoot;
  return sha256.convert(utf8.encode(identity)).toString();
}

String containedFile(String canonicalRoot, String path) {
  final resolved = File(path).resolveSymbolicLinksSync();
  final root = Platform.isWindows ? canonicalRoot.toLowerCase() : canonicalRoot;
  final candidate = Platform.isWindows ? resolved.toLowerCase() : resolved;
  if (candidate != root &&
      !candidate.startsWith('$root${Platform.pathSeparator}')) {
    throw const FileSystemException('outside workspace');
  }
  return resolved;
}

String relativeFile(String canonicalRoot, String path) => path
    .substring(canonicalRoot.length + 1)
    .replaceAll(Platform.pathSeparator, '/');

String absoluteFile(String canonicalRoot, String relative) =>
    '$canonicalRoot${Platform.pathSeparator}'
    '${relative.replaceAll('/', Platform.pathSeparator)}';

bool _sameBytes(List<int> left, List<int> right) {
  if (left.length != right.length) return false;
  for (var index = 0; index < left.length; index++) {
    if (left[index] != right[index]) return false;
  }
  return true;
}

String codeTextSha256(String text) =>
    sha256.convert(utf8.encode(text)).toString();
