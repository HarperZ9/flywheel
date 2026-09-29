// gateway_process_workdir_test.dart - where and how the app starts its engine.
//
// F-6: lane children inherit the engine's working directory, so the bundled
// engine starts in the install folder, not wherever the app was opened. The
// app passes --desktop-launch so the engine runs its start probe, which a
// plain `flywheel up` never does. The PATH fallback passes neither: an older
// engine there would refuse the flag, and `flywheel up` picks its own folder.
import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/services/gateway_process.dart';

class _Launch {
  _Launch(this.executable, this.arguments, this.workingDirectory);
  final String executable;
  final List<String> arguments;
  final String? workingDirectory;
}

GatewayProcess _gateway(List<_Launch> launches, {String? bundled}) =>
    GatewayProcess(
      bundledEngineResolver: () => bundled,
      processStarter: (exe, args,
          {required mode, required runInShell, workingDirectory}) async {
        launches.add(_Launch(exe, args, workingDirectory));
        return _Child();
      },
    );

void main() {
  test('the bundled engine starts in the install folder with the flag',
      () async {
    final launches = <_Launch>[];
    final gateway = _gateway(launches,
        bundled: 'C:/Apps With Spaces/engine/flywheel-gateway.exe');
    expect(await gateway.start(port: 8801), isNull);
    final launch = launches.single;
    expect(launch.arguments, ['--port', '8801', '--desktop-launch']);
    expect(launch.workingDirectory, 'C:/Apps With Spaces');
    expect(launch.workingDirectory, isNot(Directory.current.path));
    gateway.stopIfOwned();
  });

  test('automatic start uses the same folder and flag', () async {
    final launches = <_Launch>[];
    final gateway = _gateway(launches,
        bundled: 'C:/Apps/Flywheel/engine/flywheel-gateway.exe');
    expect(await gateway.startBundled(), isNull);
    expect(launches.single.arguments, contains('--desktop-launch'));
    expect(launches.single.workingDirectory, 'C:/Apps/Flywheel');
    gateway.stopIfOwned();
  });

  test('the PATH fallback passes no flag and keeps its own folder',
      () async {
    final launches = <_Launch>[];
    final gateway = _gateway(launches);
    expect(await gateway.start(), isNull);
    expect(launches.single.arguments, ['up', '--port', '8799']);
    expect(launches.single.workingDirectory, isNull);
    gateway.stopIfOwned();
  });

  test('the install folder is the parent of an engine folder only', () {
    final sep = Platform.pathSeparator;
    final root = 'C:${sep}Apps${sep}Flywheel';
    expect(
        GatewayProcess.installFolderFor(
            GatewayProcess.bundledEnginePathFor(root)),
        root);
    expect(GatewayProcess.installFolderFor('C:${sep}Tools${sep}gw.exe'),
        'C:${sep}Tools');
  });
}

class _Child implements Process {
  final _exit = Completer<int>();
  @override
  IOSink get stdin => IOSink(StreamController<List<int>>().sink);
  @override
  Stream<List<int>> get stdout => const Stream.empty();
  @override
  Stream<List<int>> get stderr => const Stream.empty();
  @override
  Future<int> get exitCode => _exit.future;
  @override
  int get pid => 1;
  @override
  bool kill([ProcessSignal signal = ProcessSignal.sigterm]) {
    if (!_exit.isCompleted) _exit.complete(0);
    return true;
  }
}
