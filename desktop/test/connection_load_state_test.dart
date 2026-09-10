import 'dart:io';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/services/connection_config.dart';

void main() {
  late Directory dir;
  late File file;
  setUp(() {
    dir = Directory.systemTemp.createTempSync('connection-load-');
    file = File('${dir.path}/connection.json');
  });
  tearDown(() => dir.deleteSync(recursive: true));

  test('only an absent saved connection is a fresh local default', () {
    final store = ConnectionStore(file: file);
    expect(store.loadState, ConnectionLoadState.unread);
    expect(store.load().isRemote, isFalse);
    expect(store.loadState, ConnectionLoadState.absent);
  });

  for (final content in ['{bad', 'null', '[]']) {
    test('invalid saved content $content is not absence', () {
      file.writeAsStringSync(content);
      final store = ConnectionStore(file: file);
      expect(store.load().isRemote, isFalse);
      expect(store.loadState, ConnectionLoadState.invalidOrUnreadable);
    });
  }

  test('explicit empty config is saved state and remains manual-only', () {
    file.writeAsStringSync('{}');
    final store = ConnectionStore(file: file)..load();
    expect(store.loadState, ConnectionLoadState.loaded);
  });

  test('a directory at the saved path cannot be absence', () {
    Directory(file.path).createSync();
    final store = ConnectionStore(file: file)..load();
    expect(store.loadState, ConnectionLoadState.invalidOrUnreadable);
  });

  test('read failure cannot be mistaken for an absent configuration', () {
    file.writeAsStringSync('{}');
    final store = ConnectionStore(file: _UnreadableFile(file.path))..load();
    expect(store.loadState, ConnectionLoadState.invalidOrUnreadable);
  });

  test('clear then load restores the fresh default classification', () {
    final store = ConnectionStore(file: file)
      ..save(const ConnectionConfig(baseUrl: 'https://paired.invalid'));
    expect(store.load().isRemote, isTrue);
    expect(store.loadState, ConnectionLoadState.loaded);
    store.clear();
    expect(store.load().isRemote, isFalse);
    expect(store.loadState, ConnectionLoadState.absent);
  });
}

class _UnreadableFile implements File {
  _UnreadableFile(this.path);
  @override
  final String path;
  @override
  String readAsStringSync({Encoding encoding = utf8}) =>
      throw const FileSystemException('synthetic access denial');
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
