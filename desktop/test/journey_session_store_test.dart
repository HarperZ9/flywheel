import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/evidence_state.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';

const _journey = 'jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _head =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _digest =
    'd8816f66d6219cab73766e8e3b9b8881e1218865ec0bb7b07bb68cd73d28dc45';
const _forbiddenSessionKeys =
    'projection,fact_ids,claim_ids,checks,verdicts,receipt,grant_ref,token,owner_ref,model,provider';

Directory _temp() {
  final directory = Directory.systemTemp.createTempSync('journey-session-');
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}

File _file(Directory directory) =>
    File('${directory.path}${Platform.pathSeparator}session.json');

Map<String, dynamic> _sessionRecord({String lens = 'Verify'}) => {
      'details_expanded': false,
      'journey_ref': _journey,
      'lens': lens,
      'recovery_visible': false,
      'schema': 'flywheel.desktop-journey-session/v1',
    };

JourneySession _session(
        {String journeyRef = _journey,
        JourneyLens lens = JourneyLens.verify,
        String? selectionRef}) =>
    JourneySession(
        journeyRef: journeyRef, lens: lens, selectionRef: selectionRef);

JourneyLocalStoreException _failure(void Function() call) {
  try {
    call();
  } on JourneyLocalStoreException catch (error) {
    return error;
  }
  fail('expected JourneyLocalStoreException');
}

void main() {
  _roundTripTests();
  _draftPublicTextTests();
  _allowlistTests();
  _corruptionTests();
  _saveEnvelopeBoundsTests();
  _atomicTests();
}

void _draftPublicTextTests() {
  test('canonical digest and public text survive immutable round trip', () {
    final draft = _payloadDraft({
      'nested': {'b': 2, 'a': 1},
      'client_request_id': 'request-1'
    });
    expect(draft.payloadSha256, _digest);
    for (final text in [
      'Résumé 😀 remains public',
      'Progress is 50% complete'
    ]) {
      final file = _file(_temp())
        ..writeAsStringSync(jsonEncode(_draftEnvelope({
          'client_request_id': 'request-public-text',
          'note': text,
        })));
      expect(JourneyDraftStore(file: file).list().single.payload['note'], text);
    }
  });
}

Map<String, dynamic> _draftEnvelope(Map<Object?, Object?> payload) {
  final draft = _payloadDraft(payload);
  return {
    'drafts': [
      {
        'base_event_head_sha256': draft.baseEventHeadSha256,
        'draft_ref': draft.draftRef,
        'journey_ref': draft.journeyRef,
        'kind': draft.kind,
        'payload': draft.payload,
        'payload_sha256': draft.payloadSha256,
        'state': 'dirty',
        'updated_at': draft.updatedAt.toIso8601String(),
      }
    ],
    'schema': 'flywheel.desktop-journey-drafts/v1',
  };
}

JourneyDraft _payloadDraft(Map<Object?, Object?> payload) => JourneyDraft(
    draftRef: 'dft_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    journeyRef: _journey,
    baseEventHeadSha256: _head,
    kind: 'append',
    payload: payload,
    state: JourneyDraftState.dirty,
    updatedAt: DateTime.utc(2026, 8, 15, 12));

void _roundTripTests() {
  test('exact lenses and closed local view fields survive reload and clear',
      () {
    final file = _file(_temp());
    final store = JourneySessionStore(file: file);
    for (final lens in [
      JourneyLens.rescue,
      JourneyLens.diagnose,
      JourneyLens.verify
    ]) {
      final session = JourneySession(
          journeyRef: _journey,
          lens: lens,
          selectionRef: 'claim-1',
          detailsExpanded: true);
      store.save(session);
      final loaded = JourneySessionStore(file: file).load();
      expect(loaded?.journeyRef, _journey);
      expect(loaded?.lens, lens);
      expect(loaded?.selectionRef, 'claim-1');
      expect(loaded?.detailsExpanded, isTrue);
      expect(loaded?.recoveryVisible, isFalse);
    }
    expect(
        JourneyDraftStore().storageFile.path, endsWith('journey-drafts.json'));
    expect(JourneySessionStore().storageFile.path,
        endsWith('journey-session.json'));
    store.clear();
    expect(store.load(), isNull);
  });
}

void _allowlistTests() {
  test('disk record contains only the exact device-session allowlist', () {
    final file = _file(_temp());
    JourneySessionStore(file: file).save(JourneySession(
        journeyRef: _journey, lens: JourneyLens.verify, recoveryVisible: true));
    final value = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    expect(value['lens'], 'Verify');
    expect(value.keys.join(','),
        'details_expanded,journey_ref,lens,recovery_visible,schema');
    expect(_forbiddenSessionKeys.split(',').any(value.containsKey), isFalse);
  });

  test('invalid refs lens and unsafe selection fail before file creation', () {
    final invalid = <JourneySession Function()>[
      () => _session(journeyRef: '../journey'),
      () => _session(lens: JourneyLens.invalidResponse),
      () => _session(selectionRef: r'C:\private\selection'),
      () => _session(selectionRef: 'password=abcdefghijklmnop'),
    ];
    for (final build in invalid) {
      final error = _failure(build);
      expect(error.failure, JourneyLocalFailure.invalidRecord);
      expect(error.toString(), isNot(contains('private')));
      expect(error.toString(), isNot(contains('password')));
    }
  });
}

void _corruptionTests() {
  test('unknown keys including truth and credentials are typed corruption', () {
    for (final extra in _forbiddenSessionKeys.split(',')) {
      final file = _file(_temp());
      final value = {..._sessionRecord(), extra: 'synthetic'};
      writeJourneyLocalObject(file, value);
      final error = _failure(JourneySessionStore(file: file).load);
      expect(error.failure, JourneyLocalFailure.corruptStore);
      expect(error.toString(), isNot(contains('synthetic')));
    }
  });

  test('unknown lens malformed JSON and oversized data fail closed', () {
    final fixtures = [
      '{',
      jsonEncode(_sessionRecord(lens: 'Unknown')),
      'x' * 1048577,
    ];
    for (final fixture in fixtures) {
      final file = _file(_temp())..writeAsStringSync(fixture);
      expect(_failure(JourneySessionStore(file: file).load).failure,
          JourneyLocalFailure.corruptStore);
    }
  });
}

Map<Object?, Object?> _nodePayload(int count) => {
      'client_request_id': 'request-bounds',
      'items': List<Object?>.filled(count, null),
    };

Map<Object?, Object?> _depthPayload(int depth) {
  Object value = 'leaf';
  for (var index = 0; index < depth; index++) {
    value = [value];
  }
  return {'client_request_id': 'request-bounds', 'value': value};
}

void _saveEnvelopeBoundsTests() {
  final cases = [
    (exact: _nodePayload(4082), over: _nodePayload(4083)),
    (exact: _depthPayload(12), over: _depthPayload(13)),
  ];

  test('read and save enforce exact complete-envelope bounds', () {
    for (final fixture in cases) {
      final store = JourneyDraftStore(file: _file(_temp()));
      store.save(_payloadDraft(fixture.exact));
      expect(store.list(), hasLength(1));
      final raw = _file(_temp())
        ..writeAsStringSync(jsonEncode(_draftEnvelope(fixture.over)));
      expect(_failure(JourneyDraftStore(file: raw).list).failure,
          JourneyLocalFailure.corruptStore);
    }
  });

  test('one-over save fails before temp and preserves readable prior bytes',
      () {
    for (final fixture in cases) {
      final file = _file(_temp());
      final baseline = JourneyDraftStore(file: file)
        ..save(_payloadDraft({'client_request_id': 'request-prior'}));
      final before = file.readAsBytesSync();
      var temporaryRequested = false;
      final guarded = JourneyDraftStore(
          file: file,
          temporaryFile: (target) {
            temporaryRequested = true;
            return File('${target.path}.unexpected.tmp');
          });
      final error = _failure(() => guarded.save(_payloadDraft(fixture.over)));
      expect(error.failure, JourneyLocalFailure.invalidRecord);
      expect(temporaryRequested, isFalse);
      expect(file.readAsBytesSync(), before);
      expect(
          baseline.list().single.payload['client_request_id'], 'request-prior');
    }
  });

  test('payload bounds remain independently closed', () {
    for (final payload in [
      _nodePayload(4096),
      _depthPayload(17),
      {'client_request_id': 'bytes', 'value': 'x' * 1048576},
    ]) {
      expect(_failure(() => _payloadDraft(payload)).failure,
          JourneyLocalFailure.invalidRecord);
    }
  });
}

void _atomicTests() {
  test('pre-rename and rename failures preserve prior session and clean temp',
      () {
    final directory = _temp();
    final file = _file(directory);
    JourneySessionStore(file: file).save(_session(lens: JourneyLens.rescue));
    final before = file.readAsBytesSync();
    final failures = [
      JourneySessionStore(
          file: file,
          beforeRename: (_) => throw const FileSystemException('synthetic')),
      JourneySessionStore(
          file: file,
          renameFile: (_, __) => throw const FileSystemException('synthetic')),
    ];
    for (final store in failures) {
      final error =
          _failure(() => store.save(_session(lens: JourneyLens.diagnose)));
      expect(error.failure, JourneyLocalFailure.writeFailed);
      expect(file.readAsBytesSync(), before);
      expect(directory.listSync().whereType<File>().length, 1);
    }
  });
}
