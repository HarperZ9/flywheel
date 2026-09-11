import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/evidence_state.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';

const _journey = 'jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _head =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _operation = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _requestSha =
    '1111111111111111111111111111111111111111111111111111111111111111';
const _forbiddenSessionKeys =
    'projection,fact_ids,claim_ids,checks,verdicts,receipt,grant_ref,token,owner_ref,model,provider,goal,prompt,result,trace,caption';

Directory _temp() {
  final directory = Directory.systemTemp.createTempSync('journey-operation-');
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}

File _file(Directory directory) =>
    File('${directory.path}${Platform.pathSeparator}session.json');

JourneySession _session({
  String journeyRef = _journey,
  JourneyLens lens = JourneyLens.verify,
  String? selectionRef,
}) =>
    JourneySession(
      journeyRef: journeyRef,
      lens: lens,
      selectionRef: selectionRef,
    );

JourneyLocalStoreException _failure(void Function() call) {
  try {
    call();
  } on JourneyLocalStoreException catch (error) {
    return error;
  }
  fail('expected JourneyLocalStoreException');
}

void main() {
  _allowlistTests();
}

void _allowlistTests() {
  test('disk record contains only the exact device-session allowlist', () {
    final file = _file(_temp());
    JourneySessionStore(file: file).save(
      JourneySession(
        journeyRef: _journey,
        lens: JourneyLens.verify,
        recoveryVisible: true,
      ),
    );
    final value = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    expect(value['lens'], 'Verify');
    expect(
      value.keys.join(','),
      'details_expanded,journey_ref,lens,recovery_visible,schema',
    );
    expect(_forbiddenSessionKeys.split(',').any(value.containsKey), isFalse);
  });

  test('operation locator stores only refs and request digest hints', () {
    final file = _file(_temp());
    JourneySessionStore(file: file).save(
      JourneySession(
        journeyRef: _journey,
        lens: JourneyLens.verify,
        operationRef: _operation,
        operationEventHeadSha256: _head,
        operationRequestSha256: _requestSha,
      ),
    );
    final value = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    expect(
      value.keys.join(','),
      'details_expanded,journey_ref,lens,operation_event_head_sha256,operation_ref,operation_request_sha256,recovery_visible,schema',
    );
    expect(value['operation_ref'], _operation);
    expect(value['operation_event_head_sha256'], _head);
    expect(value['operation_request_sha256'], _requestSha);
    expect(_forbiddenSessionKeys.split(',').any(value.containsKey), isFalse);

    final loaded = JourneySessionStore(file: file).load();
    expect(loaded?.operationRef, _operation);
    expect(loaded?.operationEventHeadSha256, _head);
    expect(loaded?.operationRequestSha256, _requestSha);
  });

  test('operation locator persists execution mode without private inputs', () {
    final file = _file(_temp());
    JourneySessionStore(file: file).save(
      JourneySession(
        journeyRef: _journey,
        lens: JourneyLens.verify,
        operationExecutionMode: 'native_cli_session',
      ),
    );
    final value = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    expect(
      value.keys.join(','),
      'details_expanded,journey_ref,lens,operation_execution_mode,recovery_visible,schema',
    );
    expect(value['operation_execution_mode'], 'native_cli_session');
    expect(_forbiddenSessionKeys.split(',').any(value.containsKey), isFalse);
    expect(JourneySessionStore(file: file).load()?.operationExecutionMode,
        'native_cli_session');
  });

  test('invalid refs lens and unsafe selection fail before file creation', () {
    final invalid = <JourneySession Function()>[
      () => _session(journeyRef: '../journey'),
      () => _session(lens: JourneyLens.invalidResponse),
      () => _session(selectionRef: r'C:\private\selection'),
      () => _session(selectionRef: 'password=abcdefghijklmnop'),
      () => JourneySession(
            journeyRef: _journey,
            lens: JourneyLens.verify,
            operationRef: 'op_bad',
            operationEventHeadSha256: _head,
          ),
      () => JourneySession(
            journeyRef: _journey,
            lens: JourneyLens.verify,
            operationRef: _operation,
            operationEventHeadSha256: 'bad',
          ),
      () => JourneySession(
            journeyRef: _journey,
            lens: JourneyLens.verify,
            operationRequestSha256: 'bad',
          ),
      () => JourneySession(
            journeyRef: _journey,
            lens: JourneyLens.verify,
            operationExecutionMode: 'codex_cli',
          ),
    ];
    for (final build in invalid) {
      final error = _failure(build);
      expect(error.failure, JourneyLocalFailure.invalidRecord);
      expect(error.toString(), isNot(contains('private')));
      expect(error.toString(), isNot(contains('password')));
    }
  });
}
