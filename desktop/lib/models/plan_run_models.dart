import 'dart:convert';
import 'package:crypto/crypto.dart';

part 'plan_run_result.dart';

const planRunLimitations = <String>[
  'forged gates ran or passed',
  'workflow output is correct',
  'provider billing or side effects',
  'general execution containment',
  'off-host authenticity or signed provenance',
  'crash coverage inside the post-dispatch/pre-commit window',
  'Plan Stop or cancellation',
  'P3-T6 receipt inclusion',
  'installed upgrade or downgrade safety',
];
final _sha = RegExp(r'^[0-9a-f]{64}$');
final _prpRef = RegExp(r'^fpr_[0-9a-f]{32}$');
final _runRef = RegExp(r'^plr_[0-9a-f]{32}$');
final _journeyRef = RegExp(r'^jrn_[0-9a-f]{32}$');
final _requestId = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$');
Set<String> _f(String value) => value.split(' ').toSet();
final _t = _f('code extraction transform analysis research writing qa general');
final _prpFields = _f('schema goal task_type intent_sha256 '
    'architecture_sha256 confidence external_gate_ratio gate_counts '
    'well_posed validation_gates prompt');
final _bindingFields = _f('schema prp_id prp prp_sha256 prompt '
    'prompt_sha256 gates gates_sha256 seal_sha256 binding_sha256');
final _receiptFields = _f('schema plan_run_ref binding journey_ref '
    'expected_event_head client_request_id operation_sha256 arguments_sha256 '
    'authorization_sha256 grant_ref_sha256 execution_plan_sha256 '
    'workflow endpoint workflow_sha256 profile_sha256 effective_system_sha256 '
    'workflow_run_sha256 workflow_status denominator does_not_prove '
    'receipt_sha256');
final _receiptPlain = _f('schema plan_run_ref binding journey_ref '
    'client_request_id workflow endpoint workflow_status denominator '
    'does_not_prove');
Never _invalid() => throw const FormatException('Invalid Plan run contract');
void _reject(bool value) => value ? _invalid() : null;
void _validateUnicode(String value) {
  for (var index = 0; index < value.length; index++) {
    final unit = value.codeUnitAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      if (++index >= value.length) _invalid();
      final low = value.codeUnitAt(index);
      if (low < 0xdc00 || low > 0xdfff) _invalid();
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      _invalid();
    }
  }
}

int _unicodeCompare(String left, String right) {
  _validateUnicode(left);
  _validateUnicode(right);
  final a = utf8.encode(left), b = utf8.encode(right);
  for (var index = 0; index < a.length && index < b.length; index++) {
    if (a[index] != b[index]) return a[index].compareTo(b[index]);
  }
  return a.length.compareTo(b.length);
}

Object? _canonical(Object? value, List<int> budget, int depth) {
  if (depth > 16 || --budget[0] < 0) return _invalid();
  if (value is String) {
    _validateUnicode(value);
    return value;
  }
  if (value == null || value is bool || value is int) return value;
  if (value is num) return _invalid();
  if (value is List) {
    return value.map((item) => _canonical(item, budget, depth + 1)).toList();
  }
  if (value is Map && value.keys.every((key) => key is String)) {
    final keys = value.keys.cast<String>().toList();
    for (final key in keys) {
      _validateUnicode(key);
    }
    keys.sort(_unicodeCompare);
    return {
      for (final key in keys) key: _canonical(value[key], budget, depth + 1)
    };
  }
  return _invalid();
}

String canonicalPlanJson(Object? v) => jsonEncode(_canonical(v, [4096], 0));
String canonicalPlanSha256(Object? value) =>
    sha256.convert(utf8.encode(canonicalPlanJson(value))).toString();
String _textSha(String value) => sha256.convert(utf8.encode(value)).toString();
Map<String, Object?> _map(Object? value) {
  final copy = _canonical(value, [4096], 0);
  return copy is Map<String, Object?> ? copy : _invalid();
}

bool _exact(Map<String, Object?> value, Set<String> fields) =>
    value.length == fields.length && value.keys.every(fields.contains);
bool _hash(Object? value, {bool empty = false}) =>
    value is String && (_sha.hasMatch(value) || empty && value.isEmpty);
Object? _freeze(Object? value) {
  if (value is List) return List<Object?>.unmodifiable(value.map(_freeze));
  if (value is Map<String, Object?>) {
    return Map<String, Object?>.unmodifiable(
        value.map((key, item) => MapEntry(key, _freeze(item))));
  }
  return value;
}

Object? _copy(Object? value) => _canonical(value, [4096], 0);
void validatePlanRunOperation(Map<String, Object?> value) {
  final required = _f('workflow profile root endpoint allow_write allow_exec '
      'binding data_refs credential_refs');
  const optional = {'test_cmd'};
  if (value.keys
          .any((key) => !required.contains(key) && !optional.contains(key)) ||
      required.any((key) => !value.containsKey(key)) ||
      ['workflow', 'profile', 'root', 'endpoint'].any((key) =>
          value[key] is! String || (value[key] as String).trim().isEmpty) ||
      value['allow_write'] is! bool ||
      value['allow_exec'] is! bool ||
      value.containsKey('test_cmd') &&
          (value['test_cmd'] is! String ||
              (value['test_cmd'] as String).trim().isEmpty) ||
      value['binding'] is! Map) {
    throw ArgumentError('Gateway operation is invalid');
  }
  try {
    PlanRunBinding.fromJson(Map<String, dynamic>.from(value['binding'] as Map));
  } on Object {
    throw ArgumentError('Gateway operation is invalid');
  }
}

final class PlanRunGate {
  final String check;
  final bool externallyCheckable;
  const PlanRunGate(this.check, this.externallyCheckable);
  Map<String, Object?> toJson() =>
      {'check': check, 'externally_checkable': externallyCheckable};
}

Map<String, Object?> _validPrp(Object? source) {
  final prp = _map(source);
  if (!_exact(prp, _prpFields)) _invalid();
  final goal = prp['goal'],
      prompt = prp['prompt'],
      confidence = prp['confidence'];
  _reject(prp['schema'] != 'flywheel.prp/v2' ||
      !_t.contains(prp['task_type']) ||
      goal is! String ||
      goal.isEmpty ||
      goal.trim() != goal ||
      utf8.encode(goal).length > 16384 ||
      prompt is! String ||
      prompt.isEmpty ||
      utf8.encode(prompt).length > 65536 ||
      confidence is! int ||
      confidence < 1 ||
      confidence > 10 ||
      prp['well_posed'] is! bool ||
      !_hash(prp['intent_sha256'], empty: true) ||
      !_hash(prp['architecture_sha256'], empty: true));
  _validGates(prp);
  return prp;
}

void _validGates(Map<String, Object?> prp) {
  final raw = prp['validation_gates'], counts = prp['gate_counts'];
  _reject(raw is! List ||
      raw.isEmpty ||
      raw.length > 64 ||
      counts is! Map ||
      counts.keys.toSet().difference({'checkable', 'total'}).isNotEmpty ||
      counts.length != 2 ||
      counts['checkable'] is! int ||
      counts['total'] is! int);
  final gates = raw as List, c = counts as Map;
  final seen = <String>{};
  var checkable = 0;
  for (final item in gates) {
    final gate = _map(item);
    final check = gate['check'], flag = gate['externally_checkable'];
    _reject(!_exact(gate, {'check', 'externally_checkable'}) ||
        check is! String ||
        check.isEmpty ||
        utf8.encode(check).length > 4096 ||
        flag is! bool ||
        !seen.add('$check\u0000$flag'));
    if (flag as bool) checkable++;
  }
  _reject(c['checkable'] != checkable || c['total'] != gates.length);
  final milli = (1000 * checkable + gates.length ~/ 2) ~/ gates.length;
  final ratio = '${milli ~/ 1000}.${(milli % 1000).toString().padLeft(3, '0')}';
  if (prp['external_gate_ratio'] != ratio) _invalid();
}

final class PlanRunBinding {
  final Map<String, Object?> _value;
  final List<PlanRunGate> gates;
  PlanRunBinding._(this._value, this.gates);
  String get prpId => _value['prp_id'] as String;
  String get prpSha256 => _value['prp_sha256'] as String;
  String get prompt => _value['prompt'] as String;
  String get promptSha256 => _value['prompt_sha256'] as String;
  String get gatesSha256 => _value['gates_sha256'] as String;
  String get sealSha256 => _value['seal_sha256'] as String;
  String get bindingSha256 => _value['binding_sha256'] as String;
  Map<String, Object?> get prp => _value['prp'] as Map<String, Object?>;
  factory PlanRunBinding.fromJson(Map<String, dynamic> source) {
    final value = _map(source);
    _reject(utf8.encode(canonicalPlanJson(value)).length > 524288 ||
        !_exact(value, _bindingFields));
    final prp = _validPrp(value['prp']);
    final rawGates = _copy(prp['validation_gates']) as List;
    final unsigned = Map<String, Object?>.from(value)..remove('binding_sha256');
    _reject(value['schema'] != 'flywheel.plan-run-binding/v1' ||
        value['prp_id'] is! String ||
        !_prpRef.hasMatch(value['prp_id'] as String) ||
        value['prompt'] != prp['prompt'] ||
        canonicalPlanJson(value['gates']) != canonicalPlanJson(rawGates) ||
        value['prp_sha256'] != canonicalPlanSha256(prp) ||
        value['prompt_sha256'] != _textSha(prp['prompt'] as String) ||
        value['gates_sha256'] != canonicalPlanSha256(rawGates) ||
        !_hash(value['seal_sha256']) ||
        value['binding_sha256'] != canonicalPlanSha256(unsigned));
    final gates = rawGates.map((item) {
      final gate = item as Map<String, Object?>;
      return PlanRunGate(
          gate['check'] as String, gate['externally_checkable'] as bool);
    }).toList();
    return PlanRunBinding._(_freeze(value) as Map<String, Object?>,
        List<PlanRunGate>.unmodifiable(gates));
  }
  Map<String, Object?> toJson() => _copy(_value) as Map<String, Object?>;
}
