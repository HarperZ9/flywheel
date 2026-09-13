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
  final String label;
  const FileSelectorInspectPicker({this.label = 'Inspect JSON'});

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
      Uint8List.fromList(await file.readAsBytes()),
      filename: inspectDisplayFilename(file.name),
    );
  }
}
