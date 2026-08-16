import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/plan_run_models.dart';

Map<String, dynamic> _fixture() => jsonDecode(
        File('../tests/fixtures/plan_run_contract_v1.json').readAsStringSync())
    as Map<String, dynamic>;

void main() {
  test('shared fixture parses with exact Python-compatible hashes', () {
    final fixture = _fixture();
    final binding =
        PlanRunBinding.fromJson(fixture['binding'] as Map<String, dynamic>);
    expect(binding.toJson(), fixture['binding']);
    expect(canonicalPlanSha256(binding.prp), fixture['prp_sha256']);
    expect(
        canonicalPlanSha256(
            binding.gates.map((gate) => gate.toJson()).toList()),
        fixture['gates_sha256']);
    expect(binding.bindingSha256,
        '9d0cf21988848a801d2e90bc9bcb67445500bfaf1ae02246f0b2706f24514f85');
  });

  test('binding keeps immutable copies', () {
    final source = Map<String, dynamic>.from(_fixture()['binding'] as Map);
    final binding = PlanRunBinding.fromJson(source);
    (source['prp'] as Map)['goal'] = 'changed';
    (source['gates'] as List).clear();
    expect(binding.prp['goal'], 'Implement stable sorting.');
    expect(binding.gates, hasLength(2));
    expect(() => binding.gates.add(const PlanRunGate('x', true)),
        throwsUnsupportedError);
  });

  test('every locally recomputable binding field fails closed', () {
    final original = _fixture()['binding'] as Map<String, dynamic>;
    for (final field in [
      'schema',
      'prp_id',
      'prp_sha256',
      'prompt',
      'prompt_sha256',
      'gates_sha256',
      'seal_sha256',
      'binding_sha256'
    ]) {
      final changed = jsonDecode(jsonEncode(original)) as Map<String, dynamic>;
      changed[field] = field == 'prompt' ? 'changed' : '0' * 64;
      expect(() => PlanRunBinding.fromJson(changed), throwsFormatException,
          reason: field);
    }
  });

  test('float bool-for-int duplicate gates and count drift are refused', () {
    final original = _fixture()['binding'] as Map<String, dynamic>;
    final mutations = <void Function(Map<String, dynamic>)>[
      (b) => (b['prp'] as Map)['confidence'] = true,
      (b) => (b['prp'] as Map)['confidence'] = 1.5,
      (b) => ((b['prp'] as Map)['gate_counts'] as Map)['total'] = 65,
      (b) => ((b['prp'] as Map)['validation_gates'] as List)
          .add(((b['prp'] as Map)['validation_gates'] as List).first),
    ];
    for (final mutate in mutations) {
      final changed = jsonDecode(jsonEncode(original)) as Map<String, dynamic>;
      mutate(changed);
      expect(() => PlanRunBinding.fromJson(changed), throwsFormatException);
    }
  });

  test('canonicalizer sorts keys, preserves arrays, and rejects non-integers',
      () {
    expect(canonicalPlanSha256({'b': 2, 'a': 1}),
        canonicalPlanSha256({'a': 1, 'b': 2}));
    expect(canonicalPlanSha256([1, 2]), isNot(canonicalPlanSha256([2, 1])));
    expect(canonicalPlanSha256({'\uE000': 1, '\u{10000}': 2}),
        '8706b5798a29d65739b3d1bbb1d009f87d005c71c8130c5353c4990c15ddfec8');
    expect(() => canonicalPlanSha256({'ratio': 0.5}), throwsFormatException);
  });

  test('canonicalizer rejects unpaired UTF-16 surrogates recursively', () {
    final invalid = <Object?>[
      {'value': '\uD800leading'},
      {'value': 'trailing\uD800'},
      {'value': '\uDC00'},
      {
        'nested': <Object?>['ok', '\uDFFF']
      },
      {'\uD800': 'key'},
      {
        'key': {'\uDC00': 'nested key'}
      },
    ];
    for (final value in invalid) {
      expect(() => canonicalPlanSha256(value), throwsFormatException,
          reason: value.toString());
    }
  });
}
