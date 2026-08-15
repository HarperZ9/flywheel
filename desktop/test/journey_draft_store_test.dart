import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/services/journey_draft_store.dart';

const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _digest =
    'd8816f66d6219cab73766e8e3b9b8881e1218865ec0bb7b07bb68cd73d28dc45';

Directory _temp() {
  final directory = Directory.systemTemp.createTempSync('journey-drafts-');
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}

File _file(Directory directory) =>
    File('${directory.path}${Platform.pathSeparator}drafts.json');

JourneyDraft _draft(String suffix,
        {JourneyDraftState state = JourneyDraftState.dirty,
        Map<Object?, Object?>? payload}) =>
    JourneyDraft(
      draftRef: 'dft_${suffix.padLeft(32, '0')}',
      journeyRef: _journey,
      baseEventHeadSha256: _head,
      kind: 'append',
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
    expect((stored['drafts'] as List).map((draft) => draft['state']), [
      'clean',
      'dirty',
      'saving',
      'saved',
      'save_failed',
      'recovery_available'
    ]);
    expect(loaded.every((draft) => draft.journeyRef == _journey), isTrue);
    expect(loaded.every((draft) => draft.baseEventHeadSha256 == _head), isTrue);
    final before = file.readAsBytesSync();
    store.save(loaded.first);
    expect(file.readAsBytesSync(), before);
    expect(store.storageFile.path, file.path);
    expect(
        JourneyDraftStore().storageFile.path, endsWith('journey-drafts.json'));
  });

  test('canonical key order produces the independently fixed payload digest',
      () {
    final draft = _draft('a', payload: {
      'nested': {'b': 2, 'a': 1},
      'client_request_id': 'request-1'
    });
    expect(draft.payloadSha256, _digest);
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

  test('depth node and byte bounds fail before touching storage', () {
    Object value = 'leaf';
    for (var index = 0; index < 17; index++) {
      value = [value];
    }
    final invalid = [
      {'client_request_id': 'depth', 'value': value},
      {'client_request_id': 'nodes', 'items': List<Object?>.filled(4096, null)},
      {'client_request_id': 'bytes', 'value': 'x' * 1048576},
    ];
    for (final payload in invalid) {
      final error = _failure(() => _draft('c', payload: payload));
      expect(error.failure, JourneyLocalFailure.invalidRecord);
    }
  });
}

void _corruptionTests() {
  test('payload tampering and duplicate refs are typed corruption', () {
    final file = _file(_temp());
    final store = JourneyDraftStore(file: file)..save(_draft('d'));
    final envelope =
        jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    final drafts = envelope['drafts'] as List<dynamic>;
    (drafts.single['payload'] as Map<String, dynamic>)['changed'] = true;
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
        'schema': 'flywheel.desktop-journey-drafts/v1',
        'drafts': [
          {'state': 'dirty'}
        ]
      },
      {'schema': 'wrong', 'drafts': <Object?>[]},
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
      {'client_request_id': 'r', 'api_key': 'synthetic-value'},
      {'client_request_id': 'r', 'client_api_key': 'synthetic-value'},
      {'client_request_id': 'r', 'access_token': 'synthetic-value'},
      {'client_request_id': 'r', 'note': 'password=abcdefghijklmnop'},
      {'client_request_id': 'r', 'note': r'C:\private\draft.json'},
      {'client_request_id': 'r', 'note': r'\\server\share\draft.json'},
      {'client_request_id': 'r', 'note': '/etc/passwd'},
      {'client_request_id': 'r', 'note': 'error FiLe:/private/draft'},
      {'client_request_id': 'r', 'note': 'f%69le:opaque'},
      {'client_request_id': 'r', 'context_ref': '../private.json'},
      {
        'client_request_id': 'r',
        'artifact_refs': ['../private.json']
      },
      {'client_request_id': 'r', 'context_ref': '/absolute.json'},
      {1: 'non-string key', 'client_request_id': 'r'},
      {'client_request_id': 'r', 'value': double.nan},
      {'client_request_id': 'r', 'value': Object()},
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
    for (final store in failures) {
      final error = _failure(() => store.save(_draft('2')));
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
        acknowledgement: const JourneyDraftAcknowledgement('request-5', _head));
    expect(store.list(), isEmpty);
  });
}
