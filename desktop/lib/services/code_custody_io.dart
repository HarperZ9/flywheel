import 'dart:io';
import 'dart:typed_data';

const codeCustodyMaxBytes = 1048576;

abstract interface class CodeCustodyReadHandle {
  int lengthSync();
  List<int> readSync(int count);
  void closeSync();
}

typedef CodeCustodyOpenHandle = CodeCustodyReadHandle Function(File file);
typedef CodeCustodyReadFile = List<int> Function(File file);

List<int> readCodeCustodyFile(File file, {CodeCustodyOpenHandle? openHandle}) {
  final handle = (openHandle ?? _open)(file);
  try {
    final length = handle.lengthSync();
    if (length < 0 || length > codeCustodyMaxBytes) {
      throw const FormatException();
    }
    final output = BytesBuilder(copy: false);
    var remaining = length;
    while (remaining > 0) {
      final chunk = handle.readSync(remaining);
      if (chunk.isEmpty || chunk.length > remaining) {
        throw const FormatException();
      }
      output.add(chunk);
      remaining -= chunk.length;
    }
    if (handle.readSync(1).isNotEmpty) throw const FormatException();
    return output.takeBytes();
  } finally {
    handle.closeSync();
  }
}

CodeCustodyReadHandle _open(File file) =>
    _RandomAccessReadHandle(file.openSync(mode: FileMode.read));

final class _RandomAccessReadHandle implements CodeCustodyReadHandle {
  const _RandomAccessReadHandle(this.handle);
  final RandomAccessFile handle;

  @override
  void closeSync() => handle.closeSync();
  @override
  int lengthSync() => handle.lengthSync();
  @override
  List<int> readSync(int count) => handle.readSync(count);
}
