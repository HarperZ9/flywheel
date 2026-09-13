import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';

import '../models/inspect_evidence_models.dart';

class PickedInspectFile {
  final Uint8List bytes;
  final String? filename;
  const PickedInspectFile(this.bytes, {this.filename});
}

abstract interface class InspectFilePicker {
  Future<PickedInspectFile?> pick();
}

final class FileSelectorInspectPicker implements InspectFilePicker {
  const FileSelectorInspectPicker();

  @override
  Future<PickedInspectFile?> pick() async {
    const jsonType = XTypeGroup(
      label: 'Inspect JSON',
      extensions: ['json'],
      mimeTypes: ['application/json'],
    );
    final file = await openFile(acceptedTypeGroups: const [jsonType]);
    if (file == null) return null;
    return PickedInspectFile(
      Uint8List.fromList(await file.readAsBytes()),
      filename: inspectDisplayFilename(file.name),
    );
  }
}
