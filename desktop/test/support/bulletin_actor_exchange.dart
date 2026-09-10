import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:crypto/crypto.dart' as crypto;
import 'package:flywheel_desktop/client/strict_plan_json.dart';

class ActorExchangeError implements Exception {
  const ActorExchangeError(this.code);
  final String code;
  @override
  String toString() => code;
}

String actorDigest(List<int> bytes) => crypto.sha256.convert(bytes).toString();
bool actorId(Object? value) =>
    value is String && RegExp(r'^[A-Za-z0-9_-]{1,128}$').hasMatch(value);
bool actorHash(Object? value) =>
    value is String && RegExp(r'^[0-9a-f]{64}$').hasMatch(value);
Never actorInvalid() => throw const ActorExchangeError('record_invalid');

void actorFields(Map<String, Object?> value, Set<String> fields) {
  if (value.length != fields.length ||
      !value.keys.every(fields.contains) ||
      value['schema_version'] is! int ||
      value['schema_version'] != 1) {
    actorInvalid();
  }
}

class ActorRecord {
  ActorRecord(List<int> bytes)
      : bytes = List.unmodifiable(bytes),
        sha256 = actorDigest(bytes),
        value = _decode(bytes);
  final List<int> bytes;
  final String sha256;
  final Map<String, Object?> value;
  static Map<String, Object?> _decode(List<int> bytes) {
    try {
      return strictPlanJsonObject(bytes);
    } on Object {
      return actorInvalid();
    }
  }
}

abstract interface class ActorRecords {
  void write(String name, Map<String, Object?> value, int maxBytes);
  Future<ActorRecord> wait(String name, int maxBytes, Duration timeout,
      {String? expectedSha});
}

/// Portable trusted-host checks, not pinned-handle/hostile-process custody.
/// Parent creates the private directory with its pinned filesystem helper.
/// An exclusive sentinel detects simple root replacement; races by another
/// same-user process remain outside this adapter's containment claim.
class ActorExchange implements ActorRecords {
  ActorExchange(String path) : root = Directory(path).absolute {
    _checkAncestors(root.path);
    _canonical = root.resolveSymbolicLinksSync();
    _marker = List.generate(32, (_) => Random.secure().nextInt(256));
    final file = File('${root.path}/actor-custody');
    file.createSync(exclusive: true);
    file.writeAsBytesSync(_marker, flush: true);
  }
  final Directory root;
  late final String _canonical;
  late final List<int> _marker;
  final _read = <String>{};
  static const names = {
    'descriptor.json',
    'proposal.json',
    'review.json',
    'decision.json',
    'dispatch-permit.json',
    'result.json',
    'ready.txt'
  };

  static void _checkAncestors(String path) {
    var current = Directory(path).absolute;
    while (true) {
      if (FileSystemEntity.typeSync(current.path, followLinks: false) !=
          FileSystemEntityType.directory) {
        actorInvalid();
      }
      if (current.parent.path == current.path) break;
      current = current.parent;
    }
  }

  File _file(String name) {
    if (!names.contains(name) &&
        !RegExp(r'^transport-(?:0[0-9]|1[01])\.json$').hasMatch(name)) {
      actorInvalid();
    }
    _checkAncestors(root.path);
    if (root.resolveSymbolicLinksSync() != _canonical) actorInvalid();
    final marker = File('${root.path}/actor-custody');
    if (FileSystemEntity.typeSync(marker.path, followLinks: false) !=
            FileSystemEntityType.file ||
        marker.lengthSync() != _marker.length ||
        actorDigest(marker.readAsBytesSync()) != actorDigest(_marker)) {
      actorInvalid();
    }
    for (final entity in root.listSync(followLinks: false)) {
      final leaf = entity.uri.pathSegments.where((v) => v.isNotEmpty).last;
      if (leaf.toLowerCase() == name.toLowerCase() && leaf != name) {
        actorInvalid();
      }
    }
    return File('${root.path}/$name');
  }

  @override
  void write(String name, Map<String, Object?> value, int maxBytes) {
    _writeBytes(name, utf8.encode(jsonEncode(value)), maxBytes);
  }

  void writeReady() =>
      _writeBytes('ready.txt', utf8.encode('BULLETIN_ACTOR_READY\n'), 64);

  void _writeBytes(String name, List<int> bytes, int maxBytes) {
    try {
      if (bytes.length > maxBytes) actorInvalid();
      final file = _file(name);
      if (FileSystemEntity.typeSync(file.path, followLinks: false) !=
          FileSystemEntityType.notFound) {
        actorInvalid();
      }
      final pending = File('${file.path}.pending');
      pending.createSync(exclusive: true);
      pending.writeAsBytesSync(bytes, flush: true);
      _file(name); // Recheck immediately before publication; no race guarantee.
      if (FileSystemEntity.typeSync(file.path, followLinks: false) !=
          FileSystemEntityType.notFound) {
        actorInvalid();
      }
      pending.renameSync(file.path);
    } on Object {
      throw const ActorExchangeError('record_write_failed');
    }
  }

  @override
  Future<ActorRecord> wait(String name, int maxBytes, Duration timeout,
      {String? expectedSha}) async {
    if (_read.contains(name)) actorInvalid();
    final watch = Stopwatch()..start();
    while (watch.elapsed < timeout) {
      try {
        final file = _file(name);
        final type = FileSystemEntity.typeSync(file.path, followLinks: false);
        if (type != FileSystemEntityType.notFound) {
          if (type != FileSystemEntityType.file ||
              file.lengthSync() > maxBytes) {
            actorInvalid();
          }
          final handle = file.openSync();
          late List<int> bytes;
          try {
            bytes = handle.readSync(maxBytes + 1);
          } finally {
            handle.closeSync();
          }
          _file(name);
          if (bytes.length > maxBytes) actorInvalid();
          final record = ActorRecord(bytes);
          if (expectedSha != null && record.sha256 != expectedSha) {
            actorInvalid();
          }
          _read.add(name);
          return record;
        }
      } on Object {
        throw const ActorExchangeError('record_read_failed');
      }
      await Future<void>.delayed(const Duration(milliseconds: 5));
    }
    throw const ActorExchangeError('record_timeout');
  }
}
