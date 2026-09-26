// run_completion_outcome.dart -- the verified / claimed / failed split.
//
// Each deliverable of a run is marked verified (a named check ran and
// passed), claimed (the model or its tool said so and nothing checked it) or
// failed. The engine records the split in the private trace
// (harness/run_completion.py) and the gateway rechecks it against the trace
// before projecting it (harness/gateway_completion_outcome.py). The desktop
// only parses the content-free projection: no paths, no text.

const completionStatuses = {'verified', 'claimed', 'failed'};
const _checks = {
  'file': {null, 'file_hash_recheck'},
  'final_answer': {null, 'test_command', 'acceptance_criteria', 'run_state'},
};
final _code = RegExp(r'^[A-Za-z][A-Za-z0-9_]{0,63}$');

Never _invalid() => throw const FormatException('Run completion is invalid');

Map<String, dynamic> _map(Object? value) {
  if (value is! Map || value.keys.any((key) => key is! String)) _invalid();
  return Map<String, dynamic>.from(value);
}

void _fields(Map<String, dynamic> value, Set<String> fields) {
  if (value.length != fields.length || !value.keys.every(fields.contains)) {
    _invalid();
  }
}

final class CompletionItem {
  /// file or final_answer.
  final String kind;

  /// verified, claimed or failed.
  final String status;

  /// The named check behind the status, or null when nothing checked it.
  final String? check;
  final String detail;

  const CompletionItem._(this.kind, this.status, this.check, this.detail);

  factory CompletionItem.fromJson(Object? raw) {
    final value = _map(raw);
    _fields(value, const {'kind', 'status', 'check', 'detail'});
    final kind = value['kind'], status = value['status'];
    final check = value['check'], detail = value['detail'];
    if (kind is! String ||
        !_checks.containsKey(kind) ||
        !completionStatuses.contains(status) ||
        !_checks[kind]!.contains(check) ||
        detail is! String ||
        !_code.hasMatch(detail) ||
        (status == 'claimed') != (check == null)) {
      _invalid();
    }
    return CompletionItem._(kind, status as String, check as String?, detail);
  }
}

final class RunCompletionOutcome {
  /// recorded, unrecorded or unverifiable.
  final String status;
  final String? verdict, reason;
  final Map<String, int> counts;
  final List<CompletionItem> items;
  final int itemsOmitted;
  final bool unbackedSuccessClaim;

  const RunCompletionOutcome._(this.status, this.verdict, this.reason,
      this.counts, this.items, this.itemsOmitted, this.unbackedSuccessClaim);

  bool get recorded => status == 'recorded';

  /// Only a recorded split with every deliverable verified is done.
  bool get done => recorded && verdict == 'verified';

  factory RunCompletionOutcome.fromJson(Object? raw) {
    final value = _map(raw);
    final status = value['status'];
    if (status == 'unrecorded') {
      _fields(value, const {'status'});
      return const RunCompletionOutcome._(
          'unrecorded', null, null, {}, [], 0, false);
    }
    if (status == 'unverifiable') {
      _fields(value, const {'status', 'reason'});
      final reason = value['reason'];
      if (reason is! String || !_code.hasMatch(reason)) _invalid();
      return RunCompletionOutcome._(
          'unverifiable', null, reason, const {}, const [], 0, false);
    }
    return _recorded(value);
  }

  static RunCompletionOutcome _recorded(Map<String, dynamic> value) {
    _fields(value, const {
      'status',
      'verdict',
      'counts',
      'items',
      'items_omitted',
      'unbacked_success_claim',
    });
    final counts = _map(value['counts']);
    _fields(counts, completionStatuses);
    final rawItems = value['items'], omitted = value['items_omitted'];
    final unbacked = value['unbacked_success_claim'];
    if (value['status'] != 'recorded' ||
        !completionStatuses.contains(value['verdict']) ||
        counts.values.any((v) => v is! int || v < 0) ||
        rawItems is! List ||
        rawItems.isEmpty ||
        omitted is! int ||
        omitted < 0 ||
        unbacked is! bool) {
      _invalid();
    }
    final items = List<CompletionItem>.unmodifiable(
        rawItems.map(CompletionItem.fromJson));
    final total = counts.values.fold<int>(0, (sum, v) => sum + (v as int));
    final failed = counts['failed'] as int, claimed = counts['claimed'] as int;
    final verdict = failed > 0 ? 'failed' : (claimed > 0 ? 'claimed' : 'verified');
    if (total != items.length + omitted ||
        value['verdict'] != verdict ||
        items.last.kind != 'final_answer') {
      _invalid();
    }
    return RunCompletionOutcome._('recorded', verdict, null,
        Map<String, int>.unmodifiable(counts.cast<String, int>()), items,
        omitted, unbacked);
  }
}
