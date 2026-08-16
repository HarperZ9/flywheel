import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import 'code_buffer_session.dart';

enum CloseChoice { save, discard, cancel }

enum UnsavedWorkScope { file, workspace, navigation, application }

final class UnsavedWorkRequest {
  UnsavedWorkRequest({
    required this.scope,
    required List<String> paths,
    this.routeId,
  }) : paths = List.unmodifiable(paths);

  final UnsavedWorkScope scope;
  final String? routeId;
  final List<String> paths;
}

typedef CloseChoicePrompt = Future<CloseChoice> Function(
    UnsavedWorkRequest request);

Future<CloseChoice> showUnsavedWorkPrompt(
    BuildContext context, UnsavedWorkRequest request) async {
  final result = await showDialog<CloseChoice>(
    context: context,
    barrierDismissible: false,
    builder: (dialogContext) => AlertDialog(
      title: const Text('Unsaved code'),
      content: Text(request.paths.join('\n')),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(dialogContext, CloseChoice.cancel),
            child: const Text('Cancel')),
        TextButton(
            onPressed: () => Navigator.pop(dialogContext, CloseChoice.discard),
            child: const Text('Discard')),
        FilledButton(
            onPressed: () => Navigator.pop(dialogContext, CloseChoice.save),
            child: const Text('Save')),
      ],
    ),
  );
  return result ?? CloseChoice.cancel;
}

final class UnsavedWorkGuard {
  UnsavedWorkGuard({required this.session, required this.prompt});

  final CodeBufferSession session;
  final CloseChoicePrompt prompt;
  bool _pending = false;

  Future<bool> requestFileClose(String path) =>
      _request(UnsavedWorkScope.file, filePath: path);

  Future<bool> requestWorkspaceClose() => _request(UnsavedWorkScope.workspace);

  Future<bool> requestNavigation(String routeId) =>
      _request(UnsavedWorkScope.navigation, routeId: routeId);

  Future<bool> requestApplicationExit() =>
      _request(UnsavedWorkScope.application);

  Future<bool> _request(UnsavedWorkScope scope,
      {String? filePath, String? routeId}) async {
    if (!session.closeAdmissionReady) return false;
    if (_pending) return false;
    final targets = _targets(filePath);
    if (targets.isEmpty) return _finish(scope, filePath);
    final textAtPrompt = {
      for (final target in targets) target.path: target.controller.text,
    };
    _pending = true;
    try {
      final choice = await prompt(UnsavedWorkRequest(
          scope: scope,
          routeId: routeId,
          paths: targets.map((file) => file.relativePath).toList()));
      if (choice == CloseChoice.cancel ||
          !_sameTargets(targets, textAtPrompt, filePath == null)) {
        return false;
      }
      for (final target in targets) {
        final accepted = choice == CloseChoice.save
            ? session.save(target.path)
            : session.discard(target.path);
        if (!accepted) return false;
      }
      return _finish(scope, filePath);
    } catch (_) {
      return false;
    } finally {
      _pending = false;
    }
  }

  List<OpenFile> _targets(String? filePath) {
    final dirty = session.openFiles.where((file) => file.dirty);
    final targets = filePath == null
        ? dirty.toList()
        : dirty
            .where((file) => _pathKey(file.path) == _pathKey(filePath))
            .toList();
    targets.sort((a, b) => a.relativePath.compareTo(b.relativePath));
    return targets;
  }

  bool _sameTargets(
      List<OpenFile> captured, Map<String, String> text, bool includeAllDirty) {
    final current = {for (final file in session.openFiles) file.path: file};
    for (final target in captured) {
      if (!identical(current[target.path], target) ||
          !target.dirty ||
          target.controller.text != text[target.path]) {
        return false;
      }
    }
    return !includeAllDirty || session.dirtyPaths.length == captured.length;
  }

  String _pathKey(String path) {
    final key = File(path)
        .absolute
        .path
        .replaceAll(RegExp(r'[\\/]'), Platform.pathSeparator);
    return Platform.isWindows ? key.toLowerCase() : key;
  }

  bool _finish(UnsavedWorkScope scope, String? filePath) => switch (scope) {
        UnsavedWorkScope.file => session.closeFile(filePath!),
        UnsavedWorkScope.workspace => session.closeWorkspace(),
        UnsavedWorkScope.navigation || UnsavedWorkScope.application => true,
      };
}
