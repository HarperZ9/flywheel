// Path canonicalization and hashing helpers for the workspace session IO.
// Split from workspace.dart to hold that file under the size guideline; a
// `part` keeps the parent library's dart:io / crypto imports and its scope.
// These stay part of the same public library surface, so importers are
// unchanged.

part of 'workspace.dart';

String canonicalWorkspaceRoot(String path) =>
    Directory(path).resolveSymbolicLinksSync();

/// A comparison key that identifies the same on-disk file across separator,
/// case, symlink, and Windows 8.3 short-name differences. It resolves the real
/// path when the target (or its parent directory) exists, so a short-form path
/// such as `RUNNER~1\...\main.dart` matches its long-form canonical, then folds
/// case on Windows where the filesystem is case-insensitive. It falls back to a
/// lexical absolute path when nothing on disk can be resolved. On POSIX with no
/// symlinks in play this returns the same value the plain absolute path did.
String canonicalPathKey(String path) {
  final resolved = _resolvedPath(path).replaceAll('/', Platform.pathSeparator);
  return Platform.isWindows ? resolved.toLowerCase() : resolved;
}

String _resolvedPath(String path) {
  try {
    return File(path).resolveSymbolicLinksSync();
  } catch (_) {
    // Target may not exist (missing/deleted file); resolve the parent instead
    // so short-name and symlink differences in the directory chain still fold.
  }
  final absolute = File(path).absolute.path;
  try {
    final normalized = absolute.replaceAll('/', Platform.pathSeparator);
    final cut = normalized.lastIndexOf(Platform.pathSeparator);
    if (cut > 0) {
      final name = normalized.substring(cut + 1);
      final parent = Directory(normalized.substring(0, cut));
      if (name.isNotEmpty && parent.existsSync()) {
        return '${parent.resolveSymbolicLinksSync()}'
            '${Platform.pathSeparator}$name';
      }
    }
  } catch (_) {
    // Fall through to the lexical absolute path.
  }
  return absolute;
}

String workspaceReference(String canonicalRoot) {
  final identity =
      Platform.isWindows ? canonicalRoot.toLowerCase() : canonicalRoot;
  return sha256.convert(utf8.encode(identity)).toString();
}

String relativeFile(String canonicalRoot, String path) => path
    .substring(canonicalRoot.length + 1)
    .replaceAll(Platform.pathSeparator, '/');

String absoluteFile(String canonicalRoot, String relative) =>
    '$canonicalRoot${Platform.pathSeparator}'
    '${relative.replaceAll('/', Platform.pathSeparator)}';

String codeTextSha256(String text) =>
    sha256.convert(utf8.encode(text)).toString();
