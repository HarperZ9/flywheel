import 'dart:ffi';
import 'dart:io';

import 'package:crypto/crypto.dart';

enum CodeDiskFailure {
  busy,
  unavailable,
  changed,
  missing,
  writeFailed,
  readbackFailed,
  safeWriteUnavailable,
}

final class WorkspaceFileException implements Exception {
  const WorkspaceFileException(this.failure);
  final CodeDiskFailure failure;
}

final class WorkspaceReadResult {
  WorkspaceReadResult(this.canonicalPath, this.sha256, List<int> bytes)
      : bytes = List.unmodifiable(bytes);
  final String canonicalPath, sha256;
  final List<int> bytes;
}

enum WorkspaceWriteDisposition { saved, alreadyWritten }

final class WorkspaceWriteResult {
  const WorkspaceWriteResult(this.disposition, this.canonicalPath, this.sha256);
  final WorkspaceWriteDisposition disposition;
  final String canonicalPath, sha256;
}

final class WorkspaceFileTransaction {
  const WorkspaceFileTransaction({this.afterHandleValidated});
  final void Function()? afterHandleValidated;
  WorkspaceReadResult read({
    required String canonicalRoot,
    required String requestedPath,
  }) {
    _admit(canonicalRoot, requestedPath);
    if (!Platform.isWindows) {
      return _portableRead(canonicalRoot, requestedPath, afterHandleValidated);
    }
    final native = _WindowsIo.open();
    int? handle;
    try {
      handle = native.openRead(requestedPath);
      final path = _contained(canonicalRoot, native.finalPath(handle));
      afterHandleValidated?.call();
      final bytes = native.readAll(handle);
      return WorkspaceReadResult(path, _digest(bytes), bytes);
    } finally {
      if (handle != null) native.close(handle);
      native.dispose();
    }
  }

  WorkspaceWriteResult compareAndWrite({
    required String canonicalRoot,
    required String requestedPath,
    required String expectedDiskSha256,
    required String bufferSha256,
    required List<int> bytes,
  }) {
    _admit(canonicalRoot, requestedPath);
    if (_digest(bytes) != bufferSha256) {
      throw const WorkspaceFileException(CodeDiskFailure.writeFailed);
    }
    if (!Platform.isWindows) {
      final current = _portableRead(canonicalRoot, requestedPath, null);
      if (current.sha256 == bufferSha256) {
        return WorkspaceWriteResult(WorkspaceWriteDisposition.alreadyWritten,
            current.canonicalPath, bufferSha256);
      }
      throw const WorkspaceFileException(CodeDiskFailure.safeWriteUnavailable);
    }
    return _windowsWrite(
        canonicalRoot, requestedPath, expectedDiskSha256, bufferSha256, bytes);
  }

  WorkspaceWriteResult _windowsWrite(String root, String requested,
      String baseline, String bufferSha, List<int> bytes) {
    final native = _WindowsIo.open();
    int? handle;
    try {
      handle = native.openWrite(requested);
      final path = _contained(root, native.finalPath(handle));
      afterHandleValidated?.call();
      final current = native.readAll(handle);
      final currentSha = _digest(current);
      if (currentSha == bufferSha) {
        return WorkspaceWriteResult(
            WorkspaceWriteDisposition.alreadyWritten, path, bufferSha);
      }
      if (currentSha != baseline) {
        throw const WorkspaceFileException(CodeDiskFailure.changed);
      }
      native.writeAll(handle, bytes);
      final readback = native.readAll(handle);
      if (readback.length != bytes.length || _digest(readback) != bufferSha) {
        throw const WorkspaceFileException(CodeDiskFailure.readbackFailed);
      }
      final second = native.openRead(requested);
      try {
        if (!native.sameFile(handle, second)) {
          throw const WorkspaceFileException(CodeDiskFailure.changed);
        }
      } finally {
        native.close(second);
      }
      return WorkspaceWriteResult(
          WorkspaceWriteDisposition.saved, path, bufferSha);
    } catch (error) {
      if (error is WorkspaceFileException) rethrow;
      throw const WorkspaceFileException(CodeDiskFailure.writeFailed);
    } finally {
      if (handle != null) native.close(handle);
      native.dispose();
    }
  }
}

WorkspaceReadResult _portableRead(
    String root, String requested, void Function()? afterValidated) {
  try {
    final path = File(requested).resolveSymbolicLinksSync();
    _contained(root, path);
    final bytes = File(path).readAsBytesSync();
    afterValidated?.call();
    return WorkspaceReadResult(path, _digest(bytes), bytes);
  } catch (error) {
    if (error is WorkspaceFileException) rethrow;
    throw const WorkspaceFileException(CodeDiskFailure.missing);
  }
}

void _admit(String root, String requested) {
  final parts = requested.replaceAll(r'\', '/').split('/');
  final badPart = parts.any((part) =>
      part == '.' || part == '..' || part.endsWith('.') || part.endsWith(' '));
  if (requested.isEmpty ||
      requested.toLowerCase().startsWith('file:') ||
      !File(requested).isAbsolute ||
      badPart) {
    throw const WorkspaceFileException(CodeDiskFailure.unavailable);
  }
}

String _contained(String root, String candidate) {
  final base = _cleanPath(root), path = _cleanPath(candidate);
  final left = Platform.isWindows ? base.toLowerCase() : base;
  final right = Platform.isWindows ? path.toLowerCase() : path;
  return right != left && !right.startsWith('$left${Platform.pathSeparator}')
      ? throw const WorkspaceFileException(CodeDiskFailure.unavailable)
      : path;
}

String _cleanPath(String value) => value
    .replaceFirst(RegExp(r'^\\\\\?\\UNC\\', caseSensitive: false), r'\\')
    .replaceFirst(RegExp(r'^\\\\\?\\'), '')
    .replaceAll('/', Platform.pathSeparator);

String _digest(List<int> bytes) => sha256.convert(bytes).toString();

final class _WindowsIo {
  _WindowsIo(DynamicLibrary library)
      : create = library.lookupFunction<_CreateN, _Create>('CreateFileW'),
        closeHandle = library.lookupFunction<_CloseN, _Close>('CloseHandle'),
        finalName = library
            .lookupFunction<_FinalN, _Final>('GetFinalPathNameByHandleW'),
        seek = library.lookupFunction<_SeekN, _Seek>('SetFilePointerEx'),
        read = library.lookupFunction<_ReadN, _Read>('ReadFile'),
        write = library.lookupFunction<_ReadN, _Read>('WriteFile'),
        truncate = library.lookupFunction<_CloseN, _Close>('SetEndOfFile'),
        flush = library.lookupFunction<_CloseN, _Close>('FlushFileBuffers'),
        info =
            library.lookupFunction<_InfoN, _Info>('GetFileInformationByHandle'),
        alloc = library.lookupFunction<_AllocN, _Alloc>('LocalAlloc'),
        free = library.lookupFunction<_FreeN, _Free>('LocalFree'),
        lastError = library.lookupFunction<_ErrorN, _Error>('GetLastError') {
    memory = alloc(0x40, _capacity + 65664);
    if (memory.address == 0) {
      throw const WorkspaceFileException(CodeDiskFailure.safeWriteUnavailable);
    }
  }

  static _WindowsIo open() {
    try {
      return _WindowsIo(DynamicLibrary.open('kernel32.dll'));
    } catch (_) {
      throw const WorkspaceFileException(CodeDiskFailure.safeWriteUnavailable);
    }
  }

  static const _capacity = 16 * 1048576;
  late final Pointer<Void> memory;
  final _Create create;
  final _Close closeHandle, truncate, flush;
  final _Final finalName;
  final _Seek seek;
  final _Read read, write;
  final _Info info;
  final _Alloc alloc;
  final _Free free;
  final _Error lastError;

  int openRead(String path) => _open(path, 0x80000000, 7);
  int openWrite(String path) => _open(path, 0xC0000000, 1);
  int _open(String path, int access, int sharing) {
    final handle = create(_wide(path), access, sharing, nullptr, 3, 0x80, 0);
    if (handle == -1) {
      final failure = {
            32: CodeDiskFailure.busy,
            2: CodeDiskFailure.missing
          }[lastError()] ??
          CodeDiskFailure.unavailable;
      throw WorkspaceFileException(failure);
    }
    return handle;
  }

  String finalPath(int handle) {
    final length = finalName(handle, _path, 32768, 0);
    if (length == 0 || length >= 32768) _fail(CodeDiskFailure.unavailable);
    return String.fromCharCodes(_path.asTypedList(length));
  }

  List<int> readAll(int handle) {
    if (seek(handle, 0, nullptr, 0) == 0 ||
        read(handle, _bytes, _capacity, _count, nullptr) == 0 ||
        _count.value == _capacity) {
      _fail(CodeDiskFailure.readbackFailed);
    }
    return List<int>.from(_bytes.asTypedList(_count.value));
  }

  void writeAll(int handle, List<int> bytes) {
    _bytes.asTypedList(bytes.length).setAll(0, bytes);
    if (seek(handle, 0, nullptr, 0) == 0 ||
        write(handle, _bytes, bytes.length, _count, nullptr) == 0 ||
        _count.value != bytes.length ||
        truncate(handle) == 0 ||
        flush(handle) == 0) {
      _fail(CodeDiskFailure.writeFailed);
    }
  }

  bool sameFile(int first, int second) {
    if (info(first, _infoA) == 0 || info(second, _infoB) == 0) {
      _fail(CodeDiskFailure.unavailable);
    }
    return _infoA[7] == _infoB[7] &&
        _infoA[11] == _infoB[11] &&
        _infoA[12] == _infoB[12];
  }

  Pointer<Uint16> _wide(String value) {
    final units = value.codeUnits;
    if (units.length >= 32768) _fail(CodeDiskFailure.unavailable);
    _path.asTypedList(units.length + 1)
      ..fillRange(0, units.length + 1, 0)
      ..setAll(0, units);
    return _path;
  }

  Pointer<Uint8> get _bytes => memory.cast();
  Pointer<Uint16> get _path => (memory.cast<Uint8>() + _capacity).cast();
  Pointer<Uint32> get _count => (_path + 32768).cast();
  Pointer<Uint32> get _infoA => _count + 1;
  Pointer<Uint32> get _infoB => _infoA + 13;
  void close(int handle) => closeHandle(handle);
  void dispose() => free(memory);
  Never _fail(CodeDiskFailure failure) => throw WorkspaceFileException(failure);
}

typedef _CreateN = IntPtr Function(
    Pointer<Uint16>, Uint32, Uint32, Pointer<Void>, Uint32, Uint32, IntPtr);
typedef _Create = int Function(
    Pointer<Uint16>, int, int, Pointer<Void>, int, int, int);
typedef _CloseN = Int32 Function(IntPtr);
typedef _Close = int Function(int);
typedef _FinalN = Uint32 Function(IntPtr, Pointer<Uint16>, Uint32, Uint32);
typedef _Final = int Function(int, Pointer<Uint16>, int, int);
typedef _SeekN = Int32 Function(IntPtr, Int64, Pointer<Int64>, Uint32);
typedef _Seek = int Function(int, int, Pointer<Int64>, int);
typedef _ReadN = Int32 Function(
    IntPtr, Pointer<Uint8>, Uint32, Pointer<Uint32>, Pointer<Void>);
typedef _Read = int Function(
    int, Pointer<Uint8>, int, Pointer<Uint32>, Pointer<Void>);
typedef _InfoN = Int32 Function(IntPtr, Pointer<Uint32>);
typedef _Info = int Function(int, Pointer<Uint32>);
typedef _AllocN = Pointer<Void> Function(Uint32, IntPtr);
typedef _Alloc = Pointer<Void> Function(int, int);
typedef _FreeN = Pointer<Void> Function(Pointer<Void>);
typedef _Free = Pointer<Void> Function(Pointer<Void>);
typedef _ErrorN = Uint32 Function();
typedef _Error = int Function();
