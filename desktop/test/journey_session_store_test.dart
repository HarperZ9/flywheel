import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/evidence_state.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';

const _journey = 'jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

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
  _allowlistTests();
  _corruptionTests();
  _atomicTests();
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
    for (final forbidden in [
      'projection',
      'fact_ids',
      'claim_ids',
      'checks',
      'verdicts',
      'receipt',
      'grant_ref',
      'token',
      'owner_ref',
      'model',
      'provider'
    ]) {
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
    for (final extra in [
      'projection',
      'fact_ids',
      'claim_ids',
      'checks',
      'verdicts',
      'receipt',
      'grant_ref',
      'token',
      'owner_ref',
      'model',
      'provider'
    ]) {
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
