part of 'plan_run_models.dart';

final _workflowFields = _f('schema workflow endpoint goal_excerpt started '
    'steps status chain_hash run_countersign');
final _countersignFields = _f('kind workflow endpoint status chain_hash '
    'n_steps stored store_chain_hash');

final class PlanRunResult {
  final Map<String, Object?> _value;
  final PlanRunBinding binding;
  PlanRunResult._(this._value, this.binding);
  String get planRunRef => _value['plan_run_ref'] as String;
  String get resultSha256 => _value['result_sha256'] as String;
  Map<String, Object?> get receipt => _value['receipt'] as Map<String, Object?>;
  Map<String, Object?> get workflowRun =>
      _value['workflow_run'] as Map<String, Object?>;

  factory PlanRunResult.fromJson(Map<String, dynamic> source) {
    final value = _map(source);
    final fields = _f('schema plan_run_ref receipt workflow_run result_sha256');
    _reject(!_exact(value, fields) ||
        value['schema'] != 'flywheel.plan-run-result/v2' ||
        value['plan_run_ref'] is! String ||
        !_runRef.hasMatch(value['plan_run_ref'] as String));
    final receipt = _map(value['receipt']);
    final workflow = _map(value['workflow_run']);
    final binding =
        _validReceipt(receipt, workflow, value['plan_run_ref'] as String);
    final unsigned = Map<String, Object?>.from(value)..remove('result_sha256');
    if (value['result_sha256'] != canonicalPlanSha256(unsigned)) _invalid();
    return PlanRunResult._(_freeze(value) as Map<String, Object?>, binding);
  }

  Map<String, Object?> toJson() => _copy(_value) as Map<String, Object?>;
}

PlanRunBinding _validReceipt(Map<String, Object?> receipt,
    Map<String, Object?> workflow, String runRef) {
  _reject(!_exact(receipt, _receiptFields) ||
      receipt['schema'] != 'flywheel.plan-run-receipt/v2' ||
      receipt['plan_run_ref'] != runRef ||
      receipt['journey_ref'] is! String ||
      !_journeyRef.hasMatch(receipt['journey_ref'] as String) ||
      receipt['expected_event_head'] is! String ||
      !_sha.hasMatch(receipt['expected_event_head'] as String) ||
      receipt['client_request_id'] is! String ||
      !_requestId.hasMatch(receipt['client_request_id'] as String) ||
      receipt['workflow'] is! String ||
      receipt['endpoint'] is! String ||
      receipt['binding'] is! Map ||
      !_validWorkflow(workflow, receipt['workflow'], receipt['endpoint']) ||
      receipt['workflow_status'] != workflow['status'] ||
      receipt['does_not_prove'] is! List ||
      canonicalPlanJson(receipt['does_not_prove']) !=
          canonicalPlanJson(planRunLimitations));
  for (final name in _receiptFields.difference(_receiptPlain)) {
    if (!_hash(receipt[name])) _invalid();
  }
  final binding = PlanRunBinding.fromJson(
      Map<String, dynamic>.from(receipt['binding'] as Map));
  final counts = binding.prp['gate_counts'] as Map;
  final steps = workflow['steps'] as List;
  final denominator = {
    'forged_gates': counts['total'],
    'checkable_gates': counts['checkable'],
    'forged_gates_executed': 0,
    'workflow_steps_recorded': steps.length
  };
  final unsigned = Map<String, Object?>.from(receipt)..remove('receipt_sha256');
  _reject(canonicalPlanJson(receipt['denominator']) !=
          canonicalPlanJson(denominator) ||
      receipt['workflow_run_sha256'] != canonicalPlanSha256(workflow) ||
      receipt['receipt_sha256'] != canonicalPlanSha256(unsigned));
  return binding;
}

bool _validWorkflow(Map<String, Object?> workflow, Object? expectedWorkflow,
    Object? expectedEndpoint) {
  final steps = workflow['steps'];
  _reject(!_exact(workflow, _workflowFields) ||
      workflow['schema'] != 'flywheel.workflow-run/v1' ||
      workflow['workflow'] is! String ||
      (workflow['workflow'] as String).isEmpty ||
      workflow['workflow'] != expectedWorkflow ||
      workflow['endpoint'] is! String ||
      (workflow['endpoint'] as String).isEmpty ||
      workflow['endpoint'] != expectedEndpoint ||
      workflow['goal_excerpt'] is! String ||
      (workflow['goal_excerpt'] as String).isEmpty ||
      workflow['started'] is! String ||
      (workflow['started'] as String).isEmpty ||
      workflow['status'] is! String ||
      (workflow['status'] as String).isEmpty ||
      steps is! List ||
      !_hash(workflow['chain_hash']) ||
      recomputeWorkflowChain(workflow) != workflow['chain_hash']);
  final runSteps = steps as List;
  final sign = _map(workflow['run_countersign']);
  final identity = {
    'kind': 'workflow-run',
    'workflow': workflow['workflow'],
    'endpoint': workflow['endpoint'],
    'status': workflow['status'],
    'chain_hash': workflow['chain_hash'],
    'n_steps': runSteps.length
  };
  return _exact(sign, _countersignFields) &&
      identity.entries.every((item) => sign[item.key] == item.value) &&
      sign['n_steps'] is int &&
      sign['stored'] is String &&
      (sign['stored'] as String).isNotEmpty &&
      _hash(sign['store_chain_hash']);
}

String recomputeWorkflowChain(Map<String, Object?> workflow) {
  final value = _map(workflow);
  final header = {
    'workflow': value['workflow'],
    'endpoint': value['endpoint'],
    'goal_excerpt': value['goal_excerpt'],
    'started': value['started']
  };
  final encoded = StringBuffer(_pythonJson(header));
  final steps = value['steps'];
  if (steps is! List) _invalid();
  for (final step in steps) {
    encoded.write(_pythonJson(step));
  }
  encoded.write(_pythonJson({'final_status': value['status']}));
  return sha256.convert(utf8.encode(encoded.toString())).toString();
}

String _pythonJson(Object? value) =>
    _pythonEncode(_canonical(value, [4096], 0));

String _pythonEncode(Object? value) {
  if (value == null) return 'null';
  if (value is bool) return value ? 'true' : 'false';
  if (value is int) return value.toString();
  if (value is String) return _pythonString(value);
  if (value is List) return '[${value.map(_pythonEncode).join(', ')}]';
  if (value is Map) {
    final keys = value.keys.cast<String>().toList()..sort(_unicodeCompare);
    return '{${keys.map((key) => '${_pythonString(key)}: ${_pythonEncode(value[key])}').join(', ')}}';
  }
  return _invalid();
}

String _pythonString(String value) {
  _validateUnicode(value);
  final output = StringBuffer('"');
  const escapes = {
    0x08: r'\b',
    0x09: r'\t',
    0x0a: r'\n',
    0x0c: r'\f',
    0x0d: r'\r',
    0x22: r'\"',
    0x5c: r'\\'
  };
  for (final unit in value.codeUnits) {
    if (escapes.containsKey(unit)) {
      output.write(escapes[unit]);
    } else if (unit >= 0x20 && unit <= 0x7e) {
      output.writeCharCode(unit);
    } else {
      output.write(r'\u');
      output.write(unit.toRadixString(16).padLeft(4, '0'));
    }
  }
  output.write('"');
  return output.toString();
}
