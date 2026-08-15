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
  _completeEnvelopeBoundsTests();
  _atomicTests();
}

void _draftPublicTextTests() {
  test('canonical key order produces the independently fixed payload digest',
      () {
    final envelope = _draftEnvelope({
      'nested': {'b': 2, 'a': 1},
      'client_request_id': 'request-1'
    });
    final record = (envelope['drafts'] as List).single as Map<String, dynamic>;
    expect(record['payload_sha256'], _digest);
  });

  for (final fixture in [
    (name: 'Unicode', text: 'Résumé 😀 remains public'),
    (name: 'literal percent', text: 'Progress is 50% complete'),
  ]) {
    test('${fixture.name} draft text survives immutable round trip', () {
      final file = _file(_temp())
        ..writeAsStringSync(jsonEncode(_draftEnvelope({
          'client_request_id': 'request-public-text',
          'note': fixture.text,
        })));
      expect(JourneyDraftStore(file: file).list().single.payload['note'],
          fixture.text);
    });
  }
}

Map<String, dynamic> _draftEnvelope(Map<Object?, Object?> payload) {
  final draft = JourneyDraft(
      draftRef: 'dft_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
      journeyRef: _journey,
      baseEventHeadSha256: _head,
      kind: 'append',
      payload: payload,
      state: JourneyDraftState.dirty,
      updatedAt: DateTime.utc(2026, 8, 15, 12));
  return {
    'schema': 'flywheel.desktop-journey-drafts/v1',
    'drafts': [
      {
        'draft_ref': draft.draftRef,
        'journey_ref': draft.journeyRef,
        'base_event_head_sha256': draft.baseEventHeadSha256,
        'kind': draft.kind,
        'payload': draft.payload,
        'payload_sha256': draft.payloadSha256,
        'state': 'dirty',
        'updated_at': draft.updatedAt.toIso8601String(),
      }
    ]
  };
}

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
        detailsExpanded: true,
        recoveryVisible: false,
      );
      store.save(session);
      final loaded = JourneySessionStore(file: file).load();
      expect(loaded?.journeyRef, _journey);
      expect(loaded?.lens, lens);
      expect(loaded?.selectionRef, 'claim-1');
      expect(loaded?.detailsExpanded, isTrue);
      expect(loaded?.recoveryVisible, isFalse);
    }
    expect(store.storageFile.path, file.path);
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
        journeyRef: _journey,
        lens: JourneyLens.verify,
        detailsExpanded: false,
        recoveryVisible: true));
    final value = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    expect(value['lens'], 'Verify');
    expect(value.keys.toSet(), {
      'schema',
      'journey_ref',
      'lens',
      'details_expanded',
      'recovery_visible'
    });
    for (final forbidden in _forbiddenSessionKeys.split(',')) {
      expect(value.containsKey(forbidden), isFalse);
    }
  });

  test('invalid refs lens and unsafe selection fail before file creation', () {
    final invalid = <JourneySession Function()>[
      () => JourneySession(journeyRef: '../journey', lens: JourneyLens.rescue),
      () => JourneySession(
          journeyRef: _journey, lens: JourneyLens.invalidResponse),
      () => JourneySession(
          journeyRef: _journey,
          lens: JourneyLens.verify,
          selectionRef: r'C:\private\selection'),
      () => JourneySession(
          journeyRef: _journey,
          lens: JourneyLens.verify,
          selectionRef: 'password=abcdefghijklmnop'),
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
      final value = {
        'schema': 'flywheel.desktop-journey-session/v1',
        'journey_ref': _journey,
        'lens': 'Verify',
        'details_expanded': false,
        'recovery_visible': false,
        extra: 'synthetic'
      };
      file.writeAsStringSync(jsonEncode(value));
      final error = _failure(JourneySessionStore(file: file).load);
      expect(error.failure, JourneyLocalFailure.corruptStore);
      expect(error.toString(), isNot(contains('synthetic')));
    }
  });

  test('unknown lens malformed JSON and oversized data fail closed', () {
    final fixtures = [
      '{',
      jsonEncode({
        'schema': 'flywheel.desktop-journey-session/v1',
        'journey_ref': _journey,
        'lens': 'Unknown',
        'details_expanded': false,
        'recovery_visible': false
      }),
      'x' * 1048577,
    ];
    for (final fixture in fixtures) {
      final file = _file(_temp())..writeAsStringSync(fixture);
      expect(_failure(JourneySessionStore(file: file).load).failure,
          JourneyLocalFailure.corruptStore);
    }
  });
}

void _completeEnvelopeBoundsTests() {
  test('complete draft envelope admits node 4096 and rejects node 4097', () {
    for (final count in [4082, 4083]) {
      final file = _file(_temp())
        ..writeAsStringSync(jsonEncode(_draftEnvelope({
          'client_request_id': 'request-nodes',
          'items': List<Object?>.filled(count, null),
        })));
      final store = JourneyDraftStore(file: file);
      if (count == 4082) {
        expect(store.list(), hasLength(1));
      } else {
        expect(_failure(store.list).failure, JourneyLocalFailure.corruptStore);
      }
    }
  });

  test('complete draft envelope admits depth 16 and rejects depth 17', () {
    for (final depth in [12, 13]) {
      Object nested = 'leaf';
      for (var index = 0; index < depth; index++) {
        nested = [nested];
      }
      final file = _file(_temp())
        ..writeAsStringSync(jsonEncode(_draftEnvelope({
          'client_request_id': 'request-depth',
          'value': nested,
        })));
      final store = JourneyDraftStore(file: file);
      if (depth == 12) {
        expect(store.list(), hasLength(1));
      } else {
        expect(_failure(store.list).failure, JourneyLocalFailure.corruptStore);
      }
    }
  });

  test('payload depth node and byte limits remain independently bounded', () {
    Object nested = 'leaf';
    for (var index = 0; index < 17; index++) {
      nested = [nested];
    }
    for (final payload in [
      {'client_request_id': 'depth', 'value': nested},
      {'client_request_id': 'nodes', 'items': List.filled(4096, null)},
      {'client_request_id': 'bytes', 'value': 'x' * 1048576},
    ]) {
      expect(_failure(() => _draftEnvelope(payload)).failure,
          JourneyLocalFailure.invalidRecord);
    }
  });
}

void _atomicTests() {
  test('pre-rename and rename failures preserve prior session and clean temp',
      () {
    final directory = _temp();
    final file = _file(directory);
    final original =
        JourneySession(journeyRef: _journey, lens: JourneyLens.rescue);
    JourneySessionStore(file: file).save(original);
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
      final error = _failure(() => store.save(
          JourneySession(journeyRef: _journey, lens: JourneyLens.diagnose)));
      expect(error.failure, JourneyLocalFailure.writeFailed);
      expect(file.readAsBytesSync(), before);
      expect(directory.listSync().whereType<File>().length, 1);
    }
  });
}
