// scope_field.dart -- read what a record covers, under either field name.
//
// Records name a `scope` list that says, in plain words, what the result
// covers. Records written before the scope migration (2026-10-23) named the
// same slot `does_not_prove` and phrased each entry as a limit. Sealed and
// stored records keep their bytes, so every desktop reader goes through this
// file and accepts both names. A record carries one of the two, never both:
// the older name marks the older schema version, and each version is read
// with its own vocabulary. This mirrors harness/scope.py.
//
// The older name appears in desktop code only through [kLegacyScopeKey];
// scripts/check_scope_migration.py holds that line.

import 'evidence_state.dart';

/// The field name new records use.
const kScopeKey = 'scope';

/// The field name records used before the scope migration.
const kLegacyScopeKey = 'does_not_prove';

/// Both names, newest first.
const kScopeKeys = [kScopeKey, kLegacyScopeKey];

/// The field name this record uses for its scope, or null when it has none.
///
/// The older name wins when present, because a pre-migration record may also
/// carry an unrelated string `scope` label beside its list.
String? scopeKeyOf(Object? record) {
  if (record is! Map) return null;
  if (record.containsKey(kLegacyScopeKey)) return kLegacyScopeKey;
  if (record.containsKey(kScopeKey)) return kScopeKey;
  return null;
}

/// The key a versioned record must use: the older name for an older-version
/// record, `scope` for a current one.
String scopeKeyFor({required bool legacy}) =>
    legacy ? kLegacyScopeKey : kScopeKey;

/// The record's scope value as stored (list or string), under either name.
Object? scopeOf(Object? record) {
  final key = scopeKeyOf(record);
  return key == null ? null : (record as Map)[key];
}

/// The record's scope as a list of strings; a stored string is one entry.
List<String> scopeStrings(Object? record) {
  final value = scopeOf(record);
  if (value == null) return const [];
  if (value is String) return value.isEmpty ? const [] : [value];
  if (value is Map) return [for (final item in value.values) '$item'];
  if (value is List) return [for (final item in value) '$item'];
  return ['$value'];
}

/// The record's scope as display text: list entries joined by [separator].
String scopeText(Object? record, {String separator = ' '}) =>
    scopeStrings(record).join(separator);

/// True when a record carries the list under both names: a contract break.
bool hasBothScopeKeys(Object? record) =>
    record is Map &&
    record.containsKey(kLegacyScopeKey) &&
    record[kScopeKey] is List;

/// Reads a scope string list through [readStringList], under the record's own
/// name. A record with neither name, or with both, reports a parse issue.
List<String> readScopeList(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final key = scopeKeyOf(json) ?? kScopeKey;
  final prefix = field.isEmpty ? key : '$field.$key';
  if (hasBothScopeKeys(json)) {
    addParseIssue(issues, prefix, json[key]);
    return const [];
  }
  return readStringList(json[key], prefix, issues);
}

/// Reads a scope text value through [readText], under the record's own name.
/// A record that carries both names reports a parse issue.
String readScopeText(Map<String, Object?> json, List<ParseIssue> issues) {
  if (json.containsKey(kScopeKey) && json.containsKey(kLegacyScopeKey)) {
    addParseIssue(issues, kScopeKey, json[kScopeKey]);
    return '';
  }
  return readText(json, scopeKeyOf(json) ?? kScopeKey, issues);
}
