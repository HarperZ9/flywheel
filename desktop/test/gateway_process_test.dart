// The installed app must find its shipped engine beside the exe and prefer
// it; a dev checkout (no engine payload) falls back to PATH. The path rule
// is pure and tested directly; existence gating is exercised on a real
// temp directory.
import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/services/gateway_process.dart';

void main() {
  test('bundled engine path is engine/flywheel-gateway.exe beside the exe', () {
    final sep = Platform.pathSeparator;
    final p = GatewayProcess.bundledEnginePathFor('C:${sep}Apps${sep}Flywheel');
    expect(
        p,
        'C:${sep}Apps${sep}Flywheel${sep}engine'
        '${sep}flywheel-gateway.exe');
  });

  test('a real engine file at that path is found, an absent one is not',
      () async {
    final dir = await Directory.systemTemp.createTemp('fw_engine_test');
    try {
      final candidate = GatewayProcess.bundledEnginePathFor(dir.path);
      expect(File(candidate).existsSync(), isFalse); // dev checkout shape
      await File(candidate).create(recursive: true); // installed shape
      expect(File(candidate).existsSync(), isTrue);
    } finally {
      await dir.delete(recursive: true);
    }
  });

  test('bundled engine uses tracked console-free direct launch', () async {
    final calls = <_Call>[];
    final child = _Child();
    final gateway = _gateway(child, calls);
    expect(await gateway.start(port: 8801), isNull);
    expect(calls.single.executable,
        'C:/Apps With Spaces/engine/flywheel-gateway.exe');
    expect(calls.single.arguments, ['--port', '8801']);
    expect(calls.single.mode, ProcessStartMode.normal);
    expect(calls.single.shell, isFalse);
    gateway.stopIfOwned();
    expect(child.killCalls, 1);
  });

  test('PATH fallback requests an executable without a shell', () async {
    final calls = <_Call>[];
    final gateway = _gateway(_Child(), calls, bundled: null);
    expect(await gateway.start(), isNull);
    expect(calls.single.executable,
        Platform.isWindows ? 'flywheel.exe' : 'flywheel');
    expect(calls.single.mode, ProcessStartMode.normal);
    expect(calls.single.shell, isFalse);
    gateway.stopIfOwned();
  });

  test('Windows script candidate is rejected before launch', () async {
    if (!Platform.isWindows) return;
    final calls = <_Call>[];
    final gateway = _gateway(_Child(), calls, bundled: 'C:/Apps/flywheel.cmd');
    expect(await gateway.start(), contains('executable'));
    expect(calls, isEmpty);
    expect(gateway.startedByUs, isFalse);
  });

  test('missing PATH executable reports script fallback is unsupported',
      () async {
    if (!Platform.isWindows) return;
    final gateway = GatewayProcess(
      bundledEngineResolver: () => null,
      processStarter: (executable, args,
          {required mode, required runInShell}) async {
        throw ProcessException(
            executable, args, 'synthetic missing executable');
      },
    );
    expect(await gateway.start(), contains('script'));
    expect(gateway.startedByUs, isFalse);
  });

  test('concurrent starts share one launch', () async {
    final pending = Completer<Process>();
    var starts = 0;
    final gateway = GatewayProcess(
      bundledEngineResolver: () => 'C:/Apps/engine.exe',
      processStarter: (_, __, {required mode, required runInShell}) {
        starts++;
        return pending.future;
      },
    );
    final first = gateway.start();
    final second = gateway.start();
    pending.complete(_Child());
    expect(await first, isNull);
    expect(await second, isNull);
    expect(starts, 1);
    gateway.stopIfOwned();
  });

  test('stop cancels pending launch and prevents a replacement until settled',
      () async {
    final pending = Completer<Process>();
    final child = _Child();
    var starts = 0;
    final gateway = GatewayProcess(
      bundledEngineResolver: () => 'C:/Apps/engine.exe',
      processStarter: (_, __, {required mode, required runInShell}) {
        starts++;
        return pending.future;
      },
    );
    final first = gateway.start();
    gateway.stopIfOwned();
    final second = gateway.start();
    pending.complete(child);
    expect(await first, contains('cancelled'));
    expect(await second, contains('cancelled'));
    expect(starts, 1);
    expect(child.killCalls, 1);
    expect(gateway.startedByUs, isFalse);
  });

  test('exited child releases ownership so start can retry', () async {
    final calls = <_Call>[];
    final child = _Child();
    final gateway = _gateway(child, calls);
    await gateway.start();
    child.exit.complete(17);
    await Future<void>.delayed(Duration.zero);
    expect(gateway.startedByUs, isFalse);
    await gateway.start();
    expect(calls, hasLength(2));
  });

  test('old child exit cannot clear newer child ownership', () async {
    final first = _Child();
    final second = _Child();
    var starts = 0;
    final gateway = GatewayProcess(
      bundledEngineResolver: () => 'C:/Apps/engine.exe',
      processStarter: (_, __, {required mode, required runInShell}) async =>
          starts++ == 0 ? first : second,
    );
    await gateway.start();
    gateway.stopIfOwned();
    await gateway.start();
    first.exit.complete(0);
    await Future<void>.delayed(Duration.zero);
    expect(gateway.startedByUs, isTrue);
    gateway.stopIfOwned();
    expect(second.killCalls, 1);
  });

  test('failed stop retains ownership for a later stop', () async {
    final child = _Child()..killResult = false;
    final gateway = _gateway(child, []);
    await gateway.start();
    gateway.stopIfOwned();
    expect(gateway.startedByUs, isTrue);
    child.killResult = true;
    gateway.stopIfOwned();
    expect(child.killCalls, 2);
    expect(gateway.startedByUs, isFalse);
  });

  test('both output streams are drained and stdin is closed', () async {
    final child = _Child();
    var drained = 0;
    Stream<List<int>> data() async* {
      for (var i = 0; i < 32; i++) {
        yield List.filled(8192, 65);
      }
      drained++;
    }

    child.out = data();
    child.err = data();
    final gateway = _gateway(child, []);
    await gateway.start();
    for (var i = 0; i < 10 && drained != 2; i++) {
      await Future<void>.delayed(Duration.zero);
    }
    expect(drained, 2);
    expect(child.inputClosed, isTrue);
    gateway.stopIfOwned();
  });

  test('output errors do not escape or prevent shutdown', () async {
    final child = _Child();
    child.out = Stream.error(StateError('synthetic stdout failure'));
    child.err = Stream.error(StateError('synthetic stderr failure'));
    final gateway = _gateway(child, []);
    expect(await gateway.start(), isNull);
    await Future<void>.delayed(Duration.zero);
    gateway.stopIfOwned();
    expect(child.killCalls, 1);
  });

  test('failed start can retry without leaving a pending launch', () async {
    var attempts = 0;
    final gateway = GatewayProcess(
      bundledEngineResolver: () => 'C:/Apps/engine.exe',
      processStarter: (exe, args, {required mode, required runInShell}) async {
        if (attempts++ == 0) throw ProcessException(exe, args);
        return _Child();
      },
    );
    expect(await gateway.start(), isNotNull);
    expect(await gateway.start(), isNull);
    expect(attempts, 2);
    gateway.stopIfOwned();
  });

  test('I/O failure is not proof that the owned process exited', () async {
    final child = _Child();
    await child.stdin.close();
    child.stdin = _BrokenInput();
    final gateway = _gateway(child, []);
    await gateway.start();
    await Future<void>.delayed(Duration.zero);
    expect(gateway.startedByUs, isTrue);
    child.exit.completeError(StateError('synthetic exit observation failure'));
    await Future<void>.delayed(Duration.zero);
    expect(gateway.startedByUs, isTrue);
    gateway.stopIfOwned();
    expect(child.killCalls, 1);
  });
}

GatewayProcess _gateway(_Child child, List<_Call> calls,
        {String? bundled =
            'C:/Apps With Spaces/engine/flywheel-gateway.exe'}) =>
    GatewayProcess(
      bundledEngineResolver: () => bundled,
      processStarter: (exe, args, {required mode, required runInShell}) async {
        calls.add(_Call(exe, args, mode, runInShell));
        return child;
      },
    );

class _Call {
  _Call(this.executable, this.arguments, this.mode, this.shell);
  final String executable;
  final List<String> arguments;
  final ProcessStartMode mode;
  final bool shell;
}

class _Child implements Process {
  _Child() {
    final input = StreamController<List<int>>();
    input.stream.listen((_) {}, onDone: () => inputClosed = true);
    stdin = IOSink(input.sink);
  }
  final exit = Completer<int>();
  int killCalls = 0;
  bool killResult = true;
  bool inputClosed = false;
  Stream<List<int>> out = const Stream.empty();
  Stream<List<int>> err = const Stream.empty();
  @override
  late IOSink stdin;
  @override
  Stream<List<int>> get stdout => out;
  @override
  Stream<List<int>> get stderr => err;
  @override
  Future<int> get exitCode => exit.future;
  @override
  int get pid => 1;
  @override
  bool kill([ProcessSignal signal = ProcessSignal.sigterm]) {
    killCalls++;
    return killResult;
  }
}

class _BrokenInput implements IOSink {
  @override
  Future<void> close() =>
      Future.error(StateError('synthetic input close failure'));
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
