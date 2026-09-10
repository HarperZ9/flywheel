// Opt-in actual Windows component test. STARTUP_FIXTURE is a private JSON file
// with bundled_executable, source_root and runtime_root paths. STARTUP_RECEIPT is the output
// path. Use an existing verified onedir gateway payload, never a shared app.
// No gateway token/key is read; only owned process/window/listener state is used.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/services/gateway_process.dart';

const _powershell = 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe';

void main() {
  test('actual Windows engine startup is console-free and owned', () async {
    const fixturePath = String.fromEnvironment('STARTUP_FIXTURE');
    const receiptPath = String.fromEnvironment('STARTUP_RECEIPT');
    if (!Platform.isWindows || fixturePath.isEmpty || receiptPath.isEmpty) {
      markTestSkipped('requires an explicit isolated Windows engine fixture');
      return;
    }
    final fixture = jsonDecode(File(fixturePath).readAsStringSync()) as Map;
    final outputProbe =
        await _buildOutputProbe(fixture['runtime_root'] as String);
    final rows = <Map<String, Object?>>[];
    for (final kind in [
      'bundled_executable',
      'path_executable',
      'output_probe'
    ]) {
      final bundled = kind != 'path_executable';
      final profile = await Directory(fixture['runtime_root'] as String)
          .createTemp(bundled ? 'bundled-' : 'path-');
      final reserved = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
      final port = reserved.port;
      await reserved.close();
      _ObservedProcess? process;
      final gateway = GatewayProcess(
        bundledEngineResolver: () => kind == 'output_probe'
            ? outputProbe
            : bundled
                ? fixture['bundled_executable'] as String
                : null,
        processStarter: (exe, args,
            {required mode, required runInShell}) async {
          expect(mode, ProcessStartMode.normal);
          expect(runInShell, isFalse);
          if (!bundled) expect(exe, 'flywheel.exe');
          process = _ObservedProcess(await Process.start(exe, args,
              mode: mode,
              runInShell: runInShell,
              includeParentEnvironment: false,
              environment: {
                'SystemRoot': 'C:/Windows',
                'WINDIR': 'C:/Windows',
                'PATH': 'C:/Windows/System32',
                'FLYWHEEL_HOME': profile.path,
                'USERPROFILE': profile.path,
                'TEMP': profile.path,
                'TMP': profile.path,
                'PYTHONNOUSERSITE': '1',
                'PYTHONPATH': fixture['source_root'] as String,
                'FLYWHEEL_REPO': fixture['source_root'] as String,
              }));
          return process!;
        },
      );
      Map<String, dynamic>? observed;
      int? exitCode;
      final row = <String, Object?>{
        'kind': kind,
        'port': port,
        'path_launcher_uses_candidate_source': !bundled,
      };
      rows.add(row);
      _writeReceipt(receiptPath, rows, complete: false);
      try {
        expect(await gateway.start(port: port), isNull);
        expect(gateway.startedByUs, isTrue);
        var ready = false;
        for (var i = 0; i < 100 && !ready; i++) {
          try {
            final socket = await Socket.connect('127.0.0.1', port,
                timeout: const Duration(milliseconds: 100));
            socket.destroy();
            ready = true;
          } on SocketException {
            await Future<void>.delayed(const Duration(milliseconds: 100));
          }
        }
        expect(ready, isTrue);
        observed = await _observe(process!.pid, port);
        row.addAll(observed);
        _writeReceipt(receiptPath, rows, complete: false);
        expect(observed['visible_windows'], 0);
        final ids = (observed['ids'] as List).cast<int>();
        expect(ids, contains(observed['listener_pid']));
      } finally {
        gateway.stopIfOwned();
        if (process != null) {
          exitCode =
              await process!.exitCode.timeout(const Duration(seconds: 10));
          row['exit_code'] = exitCode;
          row['stdout_bytes_drained'] = process!.stdoutBytes;
          row['stderr_bytes_drained'] = process!.stderrBytes;
          _writeReceipt(receiptPath, rows, complete: false);
        }
      }
      await Future<void>.delayed(const Duration(milliseconds: 500));
      expect(gateway.startedByUs, isFalse);
      final ids = (observed['ids'] as List).cast<int>();
      final remaining = await _run(
          '@(Get-Process -Id ${ids.join(',')} -ErrorAction SilentlyContinue).Count');
      row['surviving_owned_processes'] = int.parse(remaining);
      _writeReceipt(receiptPath, rows, complete: false);
      expect(int.parse(remaining), 0);
      if (kind == 'output_probe') {
        expect(process!.stdoutBytes, 262144);
        expect(process!.stderrBytes, 262144);
      }
    }
    _writeReceipt(receiptPath, rows, complete: true);
  }, timeout: const Timeout(Duration(minutes: 2)));
}

void _writeReceipt(String path, List<Map<String, Object?>> rows,
    {required bool complete}) {
  File(path).writeAsStringSync(const JsonEncoder.withIndent('  ').convert({
    'schema': 'flywheel.windows-startup-component/v1',
    'complete': complete,
    'cases': rows,
    'does_not_prove': [
      'installer or full GUI launch',
      'every arbitrary executable wrapper',
      'OAuth or credential readiness',
    ],
  }));
}

Future<String> _buildOutputProbe(String root) async {
  final directory = await Directory(root).createTemp('output-probe-');
  final source = File('${directory.path}/OutputProbe.cs');
  source.writeAsStringSync(r'''
using System;
using System.Net;
using System.Net.Sockets;
using System.Threading;
public class OutputProbe {
  public static void Main(string[] args) {
    int port = int.Parse(args[args.Length - 1]);
    Console.Out.Write(new string('o', 262144));
    Console.Out.Flush();
    Console.Error.Write(new string('e', 262144));
    Console.Error.Flush();
    var listener = new TcpListener(IPAddress.Loopback, port);
    listener.Start();
    Thread.Sleep(Timeout.Infinite);
  }
}
''');
  final compiled = await Process.run(
    'C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe',
    ['/nologo', '/target:exe', '/out:OutputProbe.exe', 'OutputProbe.cs'],
    workingDirectory: directory.path,
  );
  if (compiled.exitCode != 0) {
    throw StateError('synthetic output fixture did not compile');
  }
  return '${directory.path}/OutputProbe.exe';
}

Future<String> _run(String command) async {
  final result =
      await Process.run(_powershell, ['-NoProfile', '-Command', command]);
  if (result.exitCode != 0) {
    throw StateError('owned-process observation failed');
  }
  return (result.stdout as String).trim();
}

Future<Map<String, dynamic>> _observe(int pid, int port) async {
  final source = r'''
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class StartupWindows {
  delegate bool Callback(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] static extern bool EnumWindows(Callback cb, IntPtr p);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  public static int Count(int[] ids) {
    var wanted = new HashSet<int>(ids); int count = 0;
    EnumWindows((h,p) => { uint pid; GetWindowThreadProcessId(h,out pid);
      if(wanted.Contains((int)pid) && IsWindowVisible(h)) count++; return true;
    }, IntPtr.Zero); return count;
  }
}
'@
''';
  final command = '''
$source
\$snapshot = @(Get-CimInstance -Query 'SELECT ProcessId,ParentProcessId FROM Win32_Process')
\$ids = @($pid)
for (\$depth = 0; \$depth -lt 8; \$depth++) {
  \$next = @(\$snapshot | Where-Object {
    \$_.ParentProcessId -in \$ids -and \$_.ProcessId -notin \$ids
  } | ForEach-Object { [int]\$_.ProcessId })
  if (\$next.Count -eq 0) { break }
  \$ids += \$next
  if (\$ids.Count -gt 64 -or \$depth -eq 7) { throw 'owned tree exceeds observer bound' }
}
\$image = (Get-CimInstance Win32_Process -Filter "ProcessId = $pid").ExecutablePath
\$listener = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop)
@{ ids = \$ids; visible_windows = [StartupWindows]::Count(\$ids);
   executable = \$image; listener_pid = [int]\$listener[0].OwningProcess } | ConvertTo-Json -Compress
''';
  return Map<String, dynamic>.from(jsonDecode(await _run(command)) as Map);
}

class _ObservedProcess implements Process {
  _ObservedProcess(this._inner);
  final Process _inner;
  int stdoutBytes = 0;
  int stderrBytes = 0;
  @override
  Stream<List<int>> get stdout => _inner.stdout.map((bytes) {
        stdoutBytes += bytes.length;
        return bytes;
      });
  @override
  Stream<List<int>> get stderr => _inner.stderr.map((bytes) {
        stderrBytes += bytes.length;
        return bytes;
      });
  @override
  IOSink get stdin => _inner.stdin;
  @override
  Future<int> get exitCode => _inner.exitCode;
  @override
  int get pid => _inner.pid;
  @override
  bool kill([ProcessSignal signal = ProcessSignal.sigterm]) =>
      _inner.kill(signal);
}
