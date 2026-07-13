// workspace.dart — the open project: directory listing with the usual
// noise ignored, and file open/save through dart:io. The desktop app reads
// and writes workspace files directly; the engine only enters when the
// agent is asked to work on the workspace.

import 'dart:io';

const _ignoredDirs = {
  '.git', 'node_modules', 'build', '.dart_tool', '__pycache__', 'dist',
  '.idea', '.vscode', '.venv', 'venv', 'target', '.next',
};

/// A file too large for the live editor opens read-only.
const int editableLimitBytes = 200 * 1024;

class WorkspaceEntry {
  final String path;
  final String name;
  final bool isDir;
  const WorkspaceEntry(
      {required this.path, required this.name, required this.isDir});
}

/// List one directory level: directories first, both alphabetical, noise
/// ignored. Throws on a missing directory; callers surface the error.
List<WorkspaceEntry> listDir(String path) {
  final entries = <WorkspaceEntry>[];
  for (final e in Directory(path).listSync(followLinks: false)) {
    final name = e.uri.pathSegments.lastWhere((s) => s.isNotEmpty,
        orElse: () => e.path);
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
  final bool readOnly;
  final String? note;
  const LoadedFile(this.content, {this.readOnly = false, this.note});
}

/// Read a file for the editor. Binary or oversized files degrade honestly
/// instead of crashing the pane.
LoadedFile loadFile(String path) {
  final f = File(path);
  final size = f.lengthSync();
  if (size > editableLimitBytes) {
    String head;
    try {
      head = String.fromCharCodes(f.readAsBytesSync().take(editableLimitBytes));
    } catch (e) {
      return LoadedFile('', readOnly: true, note: 'unreadable: $e');
    }
    return LoadedFile(head,
        readOnly: true,
        note:
            'large file: showing the first ${editableLimitBytes ~/ 1024} KB read-only');
  }
  try {
    return LoadedFile(f.readAsStringSync());
  } on FileSystemException catch (e) {
    return LoadedFile('', readOnly: true, note: 'unreadable: ${e.message}');
  } on FormatException {
    return const LoadedFile('',
        readOnly: true, note: 'binary file: not editable here');
  }
}

void saveFile(String path, String content) {
  File(path).writeAsStringSync(content);
}
