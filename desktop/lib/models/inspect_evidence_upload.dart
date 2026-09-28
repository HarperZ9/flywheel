import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;

import 'gateway_grant_models.dart';

const int maxInspectEvidenceUploadBytes = 16 * 1024 * 1024;
const int maxInspectUnitContractUploadBytes = 8 * 1024 * 1024;

final _asciiBasename = RegExp(r'^[A-Za-z0-9._ -]{1,120}$');

class InspectEvidenceUploadException implements Exception {
  final String code, message;
  const InspectEvidenceUploadException(this.code, this.message);
}

class InspectUnitContractUpload {
  final Uint8List bytes;
  final String sha256;
  final int byteLength;
  final String? filename;

  InspectUnitContractUpload._({
    required this.bytes,
    required this.sha256,
    required this.byteLength,
    required this.filename,
  });

  factory InspectUnitContractUpload.fromBytes(
    Uint8List bytes, {
    String? filename,
  }) {
    if (bytes.isEmpty) {
      throw const InspectEvidenceUploadException(
        'INVALID_LENGTH',
        'Inspect scorer-unit sidecar must not be empty',
      );
    }
    if (bytes.length > maxInspectUnitContractUploadBytes) {
      throw const InspectEvidenceUploadException(
        'PAYLOAD_TOO_LARGE',
        'Inspect scorer-unit sidecar is over 8 MiB',
      );
    }
    return InspectUnitContractUpload._(
      bytes: Uint8List.fromList(bytes),
      sha256: crypto.sha256.convert(bytes).toString(),
      byteLength: bytes.length,
      filename: inspectDisplayFilename(filename),
    );
  }
}

class InspectEvidenceUpload {
  final Uint8List bytes;
  final String sha256;
  final int byteLength;
  final String? filename;
  final String clientRequestId;
  final InspectUnitContractUpload? unitContract;

  InspectEvidenceUpload._({
    required this.bytes,
    required this.sha256,
    required this.byteLength,
    required this.filename,
    required this.clientRequestId,
    required this.unitContract,
  });

  factory InspectEvidenceUpload.fromBytes(
    Uint8List bytes, {
    String? filename,
    String? clientRequestId,
    InspectUnitContractUpload? unitContract,
  }) {
    if (bytes.isEmpty) {
      throw const InspectEvidenceUploadException(
        'INVALID_LENGTH',
        'Inspect JSON must not be empty',
      );
    }
    if (bytes.length > maxInspectEvidenceUploadBytes) {
      throw const InspectEvidenceUploadException(
        'PAYLOAD_TOO_LARGE',
        'Inspect JSON is over 16 MiB',
      );
    }
    final digest = crypto.sha256.convert(bytes).toString();
    return InspectEvidenceUpload._(
      bytes: Uint8List.fromList(bytes),
      sha256: digest,
      byteLength: bytes.length,
      filename: inspectDisplayFilename(filename),
      clientRequestId:
          clientRequestId ?? 'inspect-${DateTime.now().microsecondsSinceEpoch}',
      unitContract: unitContract,
    );
  }

  factory InspectEvidenceUpload.forTest({
    required Uint8List bytes,
    required String sha256,
    required int byteLength,
    required String clientRequestId,
    String? filename,
    InspectUnitContractUpload? unitContract,
  }) =>
      InspectEvidenceUpload._(
        bytes: bytes,
        sha256: sha256,
        byteLength: byteLength,
        filename: inspectDisplayFilename(filename),
        clientRequestId: clientRequestId,
        unitContract: unitContract,
      );

  InspectEvidenceUpload withUnitContract(
    InspectUnitContractUpload unitContract,
  ) =>
      InspectEvidenceUpload._(
        bytes: Uint8List.fromList(bytes),
        sha256: sha256,
        byteLength: byteLength,
        filename: filename,
        clientRequestId: clientRequestId,
        unitContract: unitContract,
      );

  String get dataRef => inspectEvidenceDataRef(sha256);

  Map<String, Object?> get source => {
        'kind': 'client-upload',
        'format': 'inspect-json',
        'sha256': sha256,
        'byte_length': byteLength,
        if (filename != null) 'filename': filename,
      };

  GatewayOperation operation() => GatewayOperation.exact(
        action: 'import.inspect',
        clientRequestId: clientRequestId,
        operation: {'source': source},
      );
}

String inspectEvidenceDataRef(String sha) =>
    'data_inspect.source:${sha.substring(0, 32)}';

String? inspectDisplayFilename(String? raw) {
  if (raw == null) return null;
  final trimmed = raw.trim();
  if (!_asciiBasename.hasMatch(trimmed) ||
      trimmed.contains('/') ||
      trimmed.contains(r'\') ||
      trimmed.contains(':') ||
      trimmed.toLowerCase().startsWith('file:')) {
    return null;
  }
  return trimmed;
}
