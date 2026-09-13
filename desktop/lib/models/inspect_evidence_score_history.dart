part of 'inspect_evidence_models.dart';

class InspectScoreHistoryCoverage {
  static const unknown = InspectScoreHistoryCoverage._(null, null, null);
  final int? present, empty, missing;
  const InspectScoreHistoryCoverage._(this.present, this.empty, this.missing);

  static InspectScoreHistoryCoverage? tryFromJson(Object? value) {
    if (value == null) {
      return null;
    }
    if (value is! Map) {
      return null;
    }
    final json = Map<String, Object?>.from(value);
    if (json.isEmpty) {
      return null;
    }
    final present = _nonnegative(json['present']);
    final empty = _nonnegative(json['empty']);
    final missing = _nonnegative(json['missing']);
    if (present == null || empty == null || missing == null) {
      return null;
    }
    return InspectScoreHistoryCoverage._(present, empty, missing);
  }

  bool get known => present != null && empty != null && missing != null;

  String get label => known
      ? 'score history present $present · empty $empty · missing $missing'
      : 'score history unknown';

  bool matches(List<InspectEvidenceRow> rows) {
    if (!known) {
      return true;
    }
    final scoreRows = rows.where((row) => row.scoreHistoryState.isNotEmpty);
    final observed = <String, int>{'present': 0, 'empty': 0, 'missing': 0};
    for (final row in scoreRows) {
      observed[row.scoreHistoryState] =
          (observed[row.scoreHistoryState] ?? 0) + 1;
    }
    return observed['present'] == present &&
        observed['empty'] == empty &&
        observed['missing'] == missing;
  }
}

class InspectScoreHistoryRowState {
  final String state, label;
  final bool invalid;
  const InspectScoreHistoryRowState(this.state, this.label, this.invalid);
}

InspectScoreHistoryRowState inspectScoreHistoryRow(Map<String, Object?> json) {
  if (!_isInspectScoreRow(json)) {
    return const InspectScoreHistoryRowState('', '', false);
  }
  if (!json.containsKey('score_history')) {
    return const InspectScoreHistoryRowState(
        'missing', 'score history unknown', false);
  }
  final history = _map(json['score_history']);
  final state = _text(history['state']);
  final events = history['events'];
  if (events is! List || !_validScoreHistoryEvents(events)) {
    return InspectScoreHistoryRowState(state, 'score history unknown', true);
  }
  return switch (state) {
    'present' when events.isNotEmpty => InspectScoreHistoryRowState(
        state, 'score history present (${events.length} events)', false),
    'empty' when events.isEmpty =>
      const InspectScoreHistoryRowState('empty', 'score history empty', false),
    _ => InspectScoreHistoryRowState(state, 'score history unknown', true),
  };
}

bool _validScoreHistoryEvents(List<Object?> events) {
  for (final event in events) {
    if (event is! Map) {
      return false;
    }
    if (!_validScoreHistoryEvent(Map<String, Object?>.from(event))) {
      return false;
    }
  }
  return true;
}

bool _validScoreHistoryEvent(Map<String, Object?> event) {
  var retained = false;
  for (final entry in event.entries) {
    switch (entry.key) {
      case 'value':
        if (!_validScoreValue(entry.value)) {
          return false;
        }
        retained = true;
      case 'reason':
        if (entry.value is! String) {
          return false;
        }
        retained = true;
      case 'provenance':
        if (!_validScoreHistoryProvenance(entry.value)) {
          return false;
        }
        retained = true;
      case 'redacted_fields':
        if (!_validRedactedFields(entry.value)) {
          return false;
        }
        retained = true;
      default:
        return false;
    }
  }
  return retained;
}

bool _validScoreValue(Object? value) {
  if (_validJsonScalar(value)) {
    return true;
  }
  if (value is List) {
    return value.every(_validJsonScalar);
  }
  if (value is Map) {
    for (final entry in value.entries) {
      if (entry.key is! String) {
        return false;
      }
      if (entry.value != null && !_validJsonScalar(entry.value)) {
        return false;
      }
    }
    return true;
  }
  return false;
}

bool _validJsonScalar(Object? value) =>
    value is String || value is bool || (value is num && value.isFinite);

bool _validScoreHistoryProvenance(Object? value) {
  if (value is! Map) {
    return false;
  }
  const safeFields = {'timestamp', 'author', 'reason'};
  for (final entry in value.entries) {
    if (entry.key is! String || !safeFields.contains(entry.key)) {
      return false;
    }
    if (entry.value is! String) {
      return false;
    }
  }
  return true;
}

bool _validRedactedFields(Object? value) {
  if (value is! List || value.isEmpty) {
    return false;
  }
  const redactedFields = {'answer', 'explanation', 'metadata'};
  final seen = <String>{};
  for (final item in value) {
    if (item is! String || !redactedFields.contains(item) || !seen.add(item)) {
      return false;
    }
  }
  return true;
}

bool _isInspectScoreRow(Map<String, Object?> json) =>
    json.containsKey('scorer') &&
    (json.containsKey('value') || json.containsKey('score_value'));

int? _nonnegative(Object? value) => value is int && value >= 0 ? value : null;
