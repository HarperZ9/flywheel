import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';

import '../models/inspect_evidence_models.dart';

class PickedInspectFile {
  final Uint8List bytes;
  final String? filename;
  const PickedInspectFile(this.bytes, {this.filename});
}

Future<Uint8List> readInspectFileBytes(XFile file, {int? maxBytes}) async {
  if (maxBytes == null) return Uint8List.fromList(await file.readAsBytes());
  final sentinel = maxBytes + 1;
  try {
    if (await file.length() > maxBytes) return Uint8List(sentinel);
  } on Object {
    // Fall back to the bounded stream path below.
  }
  final builder = BytesBuilder(copy: false);
  await for (final chunk in file.openRead(0, sentinel)) {
    builder.add(chunk);
    if (builder.length > maxBytes) return Uint8List(sentinel);
  }
  return builder.takeBytes();
}

abstract interface class InspectFilePicker {
  Future<PickedInspectFile?> pick();
}

final class FileSelectorInspectPicker implements InspectFilePicker {
  final String label;
  final int? maxBytes;
  const FileSelectorInspectPicker({
    this.label = 'Inspect JSON',
    this.maxBytes,
  });

  @override
  Future<PickedInspectFile?> pick() async {
    final jsonType = XTypeGroup(
      label: label,
      extensions: ['json'],
      mimeTypes: ['application/json'],
    );
    final file = await openFile(acceptedTypeGroups: [jsonType]);
    if (file == null) return null;
    return PickedInspectFile(
      await readInspectFileBytes(file, maxBytes: maxBytes),
      filename: inspectDisplayFilename(file.name),
    );
  }
}
