// registry_models.dart - the engine's registries, parsed defensively.
//
// Every one of these can be legitimately empty. An empty registry is a real
// state and reads as empty, never as a failure and never as "not loaded".

/// A registry that reports a count alongside its rows. The count is the
/// engine's, not `rows.length`: if the two disagree the engine has more to
/// say than this page is showing, and inventing agreement would hide that.
class NamedRegistry {
  final String schema;
  final List<String> names;
  final int count;
  final String? error;

  const NamedRegistry({
    this.schema = '',
    this.names = const [],
    this.count = 0,
    this.error,
  });

  /// [key] is the list field: 'hooks', 'skills', 'packs'.
  factory NamedRegistry.fromJson(Map<String, dynamic> json, String key) {
    final err = json['error'];
    if (err is String && err.isNotEmpty) return NamedRegistry(error: err);
    final raw = json[key];
    final names = <String>[];
    if (raw is List) {
      for (final row in raw) {
        if (row is Map && row['name'] != null) {
          names.add('${row['name']}');
        } else if (row is String) {
          names.add(row);
        }
      }
    }
    return NamedRegistry(
      schema: '${json['schema'] ?? ''}',
      names: names,
      count: json['count'] is int ? json['count'] as int : names.length,
    );
  }

  bool get isEmpty => count == 0 && names.isEmpty;

  /// True when the engine's count and the rows it sent disagree. Surfaced
  /// rather than smoothed over.
  bool get countDisagrees => names.isNotEmpty && count != names.length;
}

/// The belief, with the digest that makes it quotable.
class Credo {
  final String text;
  final String sha256;
  final String? error;

  const Credo({this.text = '', this.sha256 = '', this.error});

  factory Credo.fromJson(Map<String, dynamic> json) {
    final err = json['error'];
    if (err is String && err.isNotEmpty) return Credo(error: err);
    return Credo(
      text: '${json['credo'] ?? ''}',
      sha256: '${json['sha256'] ?? ''}',
    );
  }
}

class LoopRow {
  final String name;
  final String question;
  final bool closed;

  const LoopRow(
      {required this.name, this.question = '', this.closed = false});

  factory LoopRow.fromJson(Map<String, dynamic> json) {
    // A loop closes when every edge it names executed. Derived from the
    // edges the engine sent rather than trusted from a summary field, so a
    // loop cannot report closed while carrying an edge that never ran.
    final edges = json['edges'];
    var closed = false;
    if (edges is List && edges.isNotEmpty) {
      closed = edges.every((e) => e is Map && e['executed'] == true);
    }
    return LoopRow(
      name: '${json['name'] ?? ''}',
      question: '${json['question'] ?? ''}',
      closed: closed,
    );
  }
}

class LoopRegister {
  final List<LoopRow> loops;
  final int closedCount;
  final int total;
  final String? error;

  const LoopRegister(
      {this.loops = const [], this.closedCount = 0, this.total = 0, this.error});

  factory LoopRegister.fromJson(Map<String, dynamic> json) {
    final err = json['error'];
    if (err is String && err.isNotEmpty) return LoopRegister(error: err);
    final raw = json['loops'];
    final rows = <LoopRow>[];
    if (raw is List) {
      for (final row in raw) {
        if (row is Map<String, dynamic>) rows.add(LoopRow.fromJson(row));
      }
    }
    return LoopRegister(
      loops: rows,
      closedCount:
          json['closed_count'] is int ? json['closed_count'] as int : 0,
      total: json['total'] is int ? json['total'] as int : rows.length,
    );
  }
}

/// Handle presence, never values. The app does not collect credentials and
/// this model has no field that could hold one.
class CredentialHandles {
  final List<String> handles;
  final String? error;

  const CredentialHandles({this.handles = const [], this.error});

  factory CredentialHandles.fromJson(Map<String, dynamic> json) {
    final err = json['error'];
    if (err is String && err.isNotEmpty) return CredentialHandles(error: err);
    final raw = json['handles'] ?? json['credential_handles'];
    final out = <String>[];
    if (raw is List) {
      for (final row in raw) {
        if (row is Map && row['ref'] != null) {
          out.add('${row['ref']}');
        } else if (row is Map && row['name'] != null) {
          out.add('${row['name']}');
        } else if (row is String) {
          out.add(row);
        }
      }
    }
    return CredentialHandles(handles: out);
  }
}
