import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;

import 'inspect_evidence_upload.dart' show inspectDisplayFilename;
import 'json_pointer_locator.dart';

const int maxProcessAuditPacketBytes = 1024 * 1024;
const String processAuditPacketSchema =
    'flywheel.incident-sim-process-audit/v1';

class ProcessAuditReviewException implements Exception {
  final String code, message;
  const ProcessAuditReviewException(this.code, this.message);
}

class ProcessAuditPacketUpload {
  final Uint8List bytes;
  final String sha256, detectedFormat;
  final int byteLength;
  final String? filename;
  final Map<String, JsonPointerLocation> _locations;

  ProcessAuditPacketUpload._({
    required this.bytes,
    required this.sha256,
    required this.byteLength,
    required this.filename,
    required this.detectedFormat,
    required Map<String, JsonPointerLocation> locations,
  }) : _locations = locations;

  factory ProcessAuditPacketUpload.fromPickedBytes(
    Uint8List picked, {
    String? filename,
  }) {
    if (picked.isEmpty) {
      throw const ProcessAuditReviewException(
        'INVALID_LENGTH',
        'Process-audit JSON must not be empty.',
      );
    }
    if (picked.length > maxProcessAuditPacketBytes) {
      throw const ProcessAuditReviewException(
        'PAYLOAD_TOO_LARGE',
        'Process-audit selection is over 1 MiB.',
      );
    }
    final selected = _innerPacketBytes(picked);
    final bytes = Uint8List.fromList(selected.bytes);
    if (bytes.isEmpty) {
      throw const ProcessAuditReviewException(
        'INVALID_LENGTH',
        'Process-audit JSON must not be empty.',
      );
    }
    return ProcessAuditPacketUpload._(
      bytes: bytes,
      sha256: crypto.sha256.convert(bytes).toString(),
      byteLength: bytes.length,
      filename: inspectDisplayFilename(filename),
      detectedFormat: selected.format,
      locations: selected.locations,
    );
  }

  JsonPointerLocation? locationFor(String pointer) => _locations[pointer];

  String get preview {
    try {
      return utf8.decode(bytes);
    } on Object {
      return 'Raw bytes are not valid UTF-8.';
    }
  }
}

({Uint8List bytes, String format, Map<String, JsonPointerLocation> locations})
    _innerPacketBytes(Uint8List picked) {
  try {
    final scan = scanJsonPointers(picked);
    final decoded = jsonDecode(scan.sourceText);
    if (decoded is Map && decoded['schema'] == processAuditPacketSchema) {
      return (
        bytes: picked,
        format: 'process-audit-packet',
        locations: scan.locations,
      );
    }
    final auditPacket = decoded is Map ? decoded['audit_packet'] : null;
    if (auditPacket is Map &&
        auditPacket['schema'] == processAuditPacketSchema) {
      final innerLocation = scan.locations['/audit_packet'];
      if (innerLocation == null) {
        throw const ProcessAuditReviewException(
          'INVALID_PACKET',
          'Outer command report does not locate audit_packet bytes.',
        );
      }
      final innerBytes = Uint8List.fromList(
        picked.sublist(innerLocation.offset, innerLocation.endOffset),
      );
      final innerScan = scanJsonPointers(innerBytes);
      return (
        bytes: innerBytes,
        format: 'outer-command-report',
        locations: innerScan.locations,
      );
    }
  } on ProcessAuditReviewException {
    rethrow;
  } on JsonPointerScanException catch (error) {
    throw ProcessAuditReviewException(error.code, error.message);
  } on FormatException catch (error) {
    throw ProcessAuditReviewException('INVALID_JSON', error.message);
  }
  throw const ProcessAuditReviewException(
    'INVALID_PACKET',
    'Select an incident-sim process-audit packet or outer command report with audit_packet.',
  );
}
