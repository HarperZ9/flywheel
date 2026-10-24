// The desktop scope reader mirrors harness/scope.py: a record names what it
// covers under `scope`, a pre-migration record under the older key, and the
// older key wins when both appear (a v1 record may carry a string `scope`
// label beside its list).
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/evidence_state.dart';
import 'package:flywheel_desktop/models/scope_field.dart';

void main() {
  test('scopeKeyOf names the key a record uses, older key first', () {
    expect(scopeKeyOf({kScopeKey: ['covered']}), kScopeKey);
    expect(scopeKeyOf({kLegacyScopeKey: ['older']}), kLegacyScopeKey);
    expect(
        scopeKeyOf({kScopeKey: 'label', kLegacyScopeKey: ['older']}),
        kLegacyScopeKey);
    expect(scopeKeyOf(<String, Object?>{}), isNull);
    expect(scopeKeyOf('not a map'), isNull);
    expect(scopeKeyFor(legacy: true), kLegacyScopeKey);
    expect(scopeKeyFor(legacy: false), kScopeKey);
  });

  test('scopeStrings reads a list, a string, or nothing', () {
    expect(scopeStrings({kScopeKey: ['a', 'b']}), ['a', 'b']);
    expect(scopeStrings({kLegacyScopeKey: 'one line'}), ['one line']);
    expect(scopeStrings({kScopeKey: ''}), isEmpty);
    expect(scopeStrings(null), isEmpty);
    expect(scopeText({kScopeKey: ['a', 'b']}), 'a b');
  });

  test('both names with a list under scope is a contract break', () {
    expect(hasBothScopeKeys({kScopeKey: ['a'], kLegacyScopeKey: ['b']}),
        isTrue);
    expect(hasBothScopeKeys({kScopeKey: 'label', kLegacyScopeKey: ['b']}),
        isFalse);
    final issues = <ParseIssue>[];
    expect(
        readScopeList({kScopeKey: ['a'], kLegacyScopeKey: ['b']}, 'row',
            issues),
        isEmpty);
    expect(issues, isNotEmpty);
  });

  test('readScopeList and readScopeText read either name', () {
    for (final key in kScopeKeys) {
      final issues = <ParseIssue>[];
      expect(readScopeList({key: ['covered']}, 'row', issues), ['covered']);
      expect(readScopeText({key: 'covered'}, issues), 'covered');
      expect(issues, isEmpty, reason: key);
    }
    final missing = <ParseIssue>[];
    readScopeList(<String, Object?>{}, 'row', missing);
    expect(missing.single.field, 'row.scope');
    final both = <ParseIssue>[];
    expect(readScopeText({kScopeKey: 'a', kLegacyScopeKey: 'b'}, both), '');
    expect(both, isNotEmpty);
  });
}
