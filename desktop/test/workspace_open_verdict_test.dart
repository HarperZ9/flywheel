// The verdict for a failed file open, and why it cannot be read off
// GetLastError alone.
//
// CreateFileW and GetLastError are two separate trips over the FFI
// boundary, and the runtime does its own work between them. The code that
// comes back is therefore not reliably the one CreateFileW set. On a
// full-suite run this was observed as code 0 for a file deleted moments
// earlier, which the old rule mapped to `unavailable`; `inspect` rethrows
// anything that is not `missing`, so a routine missing file became a
// session that refused to recover and offered the operator a draft-store
// error instead of the file it was actually about.
//
// The clobber is timing-dependent and cannot be provoked on demand, so the
// decision is tested apart from the syscall: `openFailureVerdict` takes the
// path and the code, and the code is supplied here. The controls matter as
// much as the case -- a rule that answered `missing` to everything would
// pass the first test and fail the rest.
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/ide/code_buffer_session.dart';
import 'package:flywheel_desktop/ide/workspace.dart' as workspace;
import 'package:flywheel_desktop/ide/workspace_file_transaction.dart';
import 'package:flywheel_desktop/services/code_draft_store.dart';

Directory _temp(String name) {
  final dir = Directory.systemTemp.createTempSync(name);
  addTearDown(() => dir.existsSync() ? dir.deleteSync(recursive: true) : null);
  return dir;
}

String _digest(String value) => sha256.convert(utf8.encode(value)).toString();

void main() {
  test('a path that resolves to nothing is missing whatever the code says', () {
    final dir = _temp('open-verdict-gone-');
    final gone = '${dir.path}/main.dart';
    // 0 is the value actually observed after a delete. 2 and 3 are what
    // Win32 reports when it is not clobbered. All three describe the same
    // file, so all three must reach the same verdict.
    for (final code in [0, 2, 3, 5, 32]) {
      expect(openFailureVerdict(gone, code), CodeDiskFailure.missing,
          reason: 'code $code on an absent path');
    }
  });

  test('a path that is still there keeps the code-specific verdict', () {
    final dir = _temp('open-verdict-present-');
    final file = File('${dir.path}/main.dart')..writeAsStringSync('baseline');
    expect(openFailureVerdict(file.path, 32), CodeDiskFailure.busy);
    expect(openFailureVerdict(file.path, 5), CodeDiskFailure.unavailable);
    expect(openFailureVerdict(file.path, 0), CodeDiskFailure.unavailable);
    // A directory where a file was expected is present, not missing.
    expect(openFailureVerdict(dir.path, 5), CodeDiskFailure.unavailable);
  });

  test('a deleted file recovers as a conflict rather than blocking', () {
    final dir = _temp('open-verdict-recover-');
    final root = Directory('${dir.path}/workspace')..createSync();
    final file = File('${root.path}/main.dart')..writeAsStringSync('baseline');
    final store = CodeDraftStore(root: Directory('${dir.path}/code'));
    store.save(
        workspaceRef:
            workspace.workspaceReference(root.resolveSymbolicLinksSync()),
        draft: CodeDraft(
            path: 'main.dart',
            diskSha256: _digest('baseline'),
            bufferSha256: _digest('draft'),
            text: 'draft',
            updatedAt: DateTime.parse('2026-08-15T12:00:00Z')));
    file.deleteSync();
    final session = CodeBufferSession(draftStore: store)
      ..openWorkspace(root.path);
    addTearDown(session.dispose);
    final outcomes = session.recover();
    expect(session.phase, CodeSessionPhase.ready,
        reason: 'failure=${session.failure} status=${session.status}');
    expect(outcomes.map((outcome) => outcome.kind),
        [CodeRecoveryKind.fileMissing]);
    expect(session.conflicts.map((conflict) => conflict.kind),
        [CodeRecoveryKind.fileMissing]);
    expect(session.openFiles.single.controller.text, 'draft');
  });
}
