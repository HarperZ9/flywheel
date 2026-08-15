import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/services/journey_draft_store.dart';

const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _newHead =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

Directory _temp() {
  final directory = Directory.systemTemp.createTempSync('journey-drafts-');
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}

File _file(Directory directory) =>
    File('${directory.path}${Platform.pathSeparator}drafts.json');

JourneyDraft _draft(String suffix,
        {JourneyDraftState state = JourneyDraftState.dirty,
        Map<Object?, Object?>? payload,
        String? journeyRef = _journey,
        String? baseEventHeadSha256 = _head,
        String kind = 'append'}) =>
    JourneyDraft(
      draftRef: 'dft_${suffix.padLeft(32, '0')}',
      journeyRef: journeyRef,
      baseEventHeadSha256: baseEventHeadSha256,
      kind: kind,
      payload: payload ??
          {
            'client_request_id': 'request-$suffix',
            'command': {
              'type': 'advance_stage',
              'context_ref': 'context/data.json'
            }
          },
      state: state,
      updatedAt: DateTime.utc(2026, 8, 15, 12),
    );

Map<Object?, Object?> _attack(Object? key, Object? value) =>
    {'client_request_id': 'r', key: value};

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
  _immutabilityAndBoundsTests();
  _corruptionTests();
  _duplicateJsonKeyTests();
  _unsafeInputTests();
  _atomicFailureTests();
  _acknowledgementDeletionTests();
}

void _roundTripTests() {
  test('all closed states round trip and records stay byte stable', () {
    final file = _file(_temp());
    final store = JourneyDraftStore(file: file);
    const states = JourneyDraftState.values;
    for (var index = 0; index < states.length; index++) {
      store.save(_draft('$index', state: states[index]));
    }
    final loaded = JourneyDraftStore(file: file).list();
    expect(loaded.map((draft) => draft.state), states);
    final stored = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    expect((stored['drafts'] as List).map((draft) => draft['state']).join(','),
        'clean,dirty,saving,saved,save_failed,recovery_available');
    final before = file.readAsBytesSync();
    store.save(loaded.first);
    expect(file.readAsBytesSync(), before);
  });
}

void _duplicateJsonKeyTests() {
  test('canonical store control reads and duplicate keys fail closed', () {
    final file = _file(_temp());
    JourneyDraftStore(file: file)
        .save(_draft('c', payload: {'client_request_id': 'request-canonical'}));
    final canonical = file.readAsStringSync();
    expect(jsonEncode(jsonDecode(canonical)), canonical);
    for (final duplicate in [
      canonical.replaceFirst('{"drafts":',
          '{"schema":"flywheel.desktop-journey-drafts/v1","drafts":'),
      canonical.replaceFirst('{"base_event_head_sha256":',
          '{"kind":"append","base_event_head_sha256":'),
      canonical.replaceFirst('{"client_request_id":',
          '{"client_request_id":"shadow","client_request_id":'),
    ]) {
      final corrupt = _file(_temp())..writeAsStringSync(duplicate);
      expect(_failure(JourneyDraftStore(file: corrupt).list).failure,
          JourneyLocalFailure.corruptStore);
    }
  });
}

void _immutabilityAndBoundsTests() {
  test('draft copies nested caller data and exposes immutable collections', () {
    final source = <Object?, Object?>{
      'client_request_id': 'request-copy',
      'nested': {
        'items': <String>['original']
      }
    };
    final draft = _draft('b', payload: source);
    ((source['nested'] as Map)['items'] as List)[0] = 'changed';
    final nested = draft.payload['nested'] as Map<String, dynamic>;
    expect((nested['items'] as List).single, 'original');
    expect(() => nested['new'] = true, throwsUnsupportedError);
    expect(() => (nested['items'] as List).add('new'), throwsUnsupportedError);
  });
}

void _corruptionTests() {
  test('payload tampering and duplicate refs are typed corruption', () {
    final file = _file(_temp());
    final store = JourneyDraftStore(file: file)..save(_draft('d'));
    final envelope =
        jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    final drafts = envelope['drafts'] as List<dynamic>;
    (drafts.single['payload'] as Map<String, dynamic>)['client_request_id'] =
        'request-changed';
    file.writeAsStringSync(jsonEncode(envelope));
    final corrupt = _failure(store.list);
    expect(corrupt.failure, JourneyLocalFailure.corruptStore);
    expect(corrupt.toString(), isNot(contains('changed')));

    final valid = JourneyDraftStore(file: _file(_temp()));
    valid.save(_draft('e'));
    final duplicate = jsonDecode(valid.storageFile.readAsStringSync());
    (duplicate['drafts'] as List).add(duplicate['drafts'][0]);
    valid.storageFile.writeAsStringSync(jsonEncode(duplicate));
    expect(_failure(valid.list).failure, JourneyLocalFailure.corruptStore);
  });

  test('unknown state malformed record and oversized file fail closed', () {
    final unknown = JourneyDraftStore(file: _file(_temp()))..save(_draft('6'));
    final envelope = jsonDecode(unknown.storageFile.readAsStringSync());
    (envelope['drafts'] as List).single['state'] = 'unknown';
    unknown.storageFile.writeAsStringSync(jsonEncode(envelope));
    expect(_failure(unknown.list).failure, JourneyLocalFailure.corruptStore);

    for (final value in [
      {
        'drafts': [
          {'state': 'dirty'}
        ],
        'schema': 'flywheel.desktop-journey-drafts/v1',
      },
      {'drafts': <Object?>[], 'schema': 'wrong'},
    ]) {
      final file = _file(_temp())..writeAsStringSync(jsonEncode(value));
      expect(_failure(JourneyDraftStore(file: file).list).failure,
          JourneyLocalFailure.corruptStore);
    }
    final large = _file(_temp())..writeAsStringSync('x' * 1048577);
    expect(_failure(JourneyDraftStore(file: large).list).failure,
        JourneyLocalFailure.corruptStore);
  });
}

void _unsafeInputTests() {
  test('secret path ref key and JSON attacks are rejected without echo', () {
    final attacks = <Map<Object?, Object?>>[
      for (final key
          in 'api_key,client_api_key,access_token,api_keys,access_tokens,'
                  'refresh_tokens,tokens,passwords,'
                  'secrets,credentials,private_keys,authorizations,cookies,'
                  'environments,envs,passwds,access_keys'
              .split(','))
        _attack(key, 'synthetic-value'),
      for (final value
          in r'password=abcdefghijklmnop|C:\private\draft.json|\\server\share\draft.json|/etc/passwd|error FiLe:/private/draft|f%69le:opaque|C%3A%5Cprivate%5Cdraft.json|%5C%5Cserver%5Cshare%5Cdraft.json|%2Fetc%2Fpasswd|password%3Dabcdefghijklmnop'
              .split('|'))
        _attack('note', value),
      for (final value
          in '../private.json|%2e%2e%2fprivate.json|/absolute.json'.split('|'))
        _attack('context_ref', value),
      _attack('artifact_refs', ['../private.json']),
      _attack('%61pi%5Fkey', 'synthetic-value'),
      _attack('nested', {'t%6Fkens': 'synthetic-value'}),
      _attack('items', [
        {'api%5Fkeys': 'synthetic-value'}
      ]),
      _attack(1, 'non-string key'),
      _attack('value', double.nan),
      _attack('value', Object()),
      for (final value in '%2G|%A|%GG|%FF'.split('|')) _attack('note', value),
    ];
    for (final attack in attacks) {
      final error = _failure(() => _draft('f', payload: attack));
      expect(error.failure, JourneyLocalFailure.invalidRecord);
      expect(error.toString(), isNot(contains('private')));
      expect(error.toString(), isNot(contains('password')));
    }
  });
}

void _atomicFailureTests() {
  test('pre-existing injected temp collision is refused without deletion', () {
    final directory = _temp();
    final file = _file(directory);
    JourneyDraftStore(file: file).save(_draft('0'));
    final before = file.readAsBytesSync();
    final collision = File('${file.path}.collision.tmp')
      ..writeAsStringSync('owned elsewhere');
    final store =
        JourneyDraftStore(file: file, temporaryFile: (_) => collision);
    expect(_failure(() => store.save(_draft('9'))).failure,
        JourneyLocalFailure.writeFailed);
    expect(file.readAsBytesSync(), before);
    expect(collision.readAsStringSync(), 'owned elsewhere');
  });

  test('pre-rename and rename failures preserve prior bytes and clean temp',
      () {
    final directory = _temp();
    final file = _file(directory);
    JourneyDraftStore(file: file).save(_draft('1'));
    final before = file.readAsBytesSync();
    final failures = <JourneyDraftStore>[
      JourneyDraftStore(
          file: file,
          beforeRename: (_) => throw const FileSystemException('synthetic')),
      JourneyDraftStore(
          file: file,
          renameFile: (_, __) => throw const FileSystemException('synthetic')),
      JourneyDraftStore(file: file, renameFile: (_, __) {}),
    ];
    for (var index = 0; index < failures.length; index++) {
      final draft = _draft(index == failures.length - 1 ? '1' : '2');
      final error = _failure(() => failures[index].save(draft));
      expect(error.failure, JourneyLocalFailure.writeFailed);
      expect(file.readAsBytesSync(), before);
      expect(directory.listSync().whereType<File>().length, 1);
    }
  });

  test('write failure is typed and does not replace its blocking file', () {
    final blocker = File('${_temp().path}${Platform.pathSeparator}blocked')
      ..writeAsStringSync('prior');
    final target = File('${blocker.path}${Platform.pathSeparator}drafts.json');
    final error =
        _failure(() => JourneyDraftStore(file: target).save(_draft('3')));
    expect(error.failure, JourneyLocalFailure.writeFailed);
    expect(blocker.readAsStringSync(), 'prior');
  });
}

void _acknowledgementDeletionTests() {
  test(
      'dirty draft survives reload failure states and malformed acknowledgements',
      () {
    final file = _file(_temp());
    final store = JourneyDraftStore(file: file)..save(_draft('4'));
    final invalid = [
      const JourneyDraftAcknowledgement('other-request', _head),
      const JourneyDraftAcknowledgement('request-4', _head),
      const JourneyDraftAcknowledgement('request-4', ''),
      const JourneyDraftAcknowledgement('request-4', 'not-a-head'),
    ];
    for (final acknowledgement in invalid) {
      final error = _failure(() => store.delete('dft_${'4'.padLeft(32, '0')}',
          acknowledgement: acknowledgement));
      expect(error.failure, JourneyLocalFailure.acknowledgementMismatch);
      expect(JourneyDraftStore(file: file).list().single.state,
          JourneyDraftState.dirty);
    }
    store.markFailed('dft_${'4'.padLeft(32, '0')}',
        updatedAt: DateTime.utc(2026, 8, 15, 13));
    expect(store.list().single.state, JourneyDraftState.saveFailed);
  });

  test('exact request id and canonical nonblank new head permit deletion', () {
    final store = JourneyDraftStore(file: _file(_temp()))..save(_draft('5'));
    store.delete('dft_${'5'.padLeft(32, '0')}',
        acknowledgement:
            const JourneyDraftAcknowledgement('request-5', _newHead));
    expect(store.list(), isEmpty);

    store.save(_draft('6',
        journeyRef: null, baseEventHeadSha256: null, kind: 'create'));
    store.delete('dft_${'6'.padLeft(32, '0')}',
        acknowledgement: const JourneyDraftAcknowledgement('request-6', _head));
    expect(store.list(), isEmpty);
  });
}
