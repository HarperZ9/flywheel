// lane_setup_list.dart - a lane's setup items, each from a real engine check,
// with the two choices a person makes in the app.
//
// Every item shows met or needed and the engine's copy. Two items carry a
// picker: node.exe for the Node lanes and the local-model project folder.
// Each choice picks what the engine runs or reads, so it goes through its own
// exact grant (settings.node_path, lane.root) and the engine checks it again
// before it keeps it. The list then reads the lane's setup again.

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/lane_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'operation_grant_sheet.dart';

const nodePathRoute = '/api/settings/node_path';
const localModelRootRoute = '/api/lanes/local-model/root';

Future<String?> _pickNodeExe() async {
  final file = await openFile(acceptedTypeGroups: const [
    XTypeGroup(label: 'node.exe', extensions: ['exe'])
  ]);
  return file?.path;
}

Future<String?> _pickFolder() => getDirectoryPath();

/// The two pickers; tests pass their own.
class LaneSetupPickers {
  final Future<String?> Function() pickNode, pickFolder;
  const LaneSetupPickers(
      {this.pickNode = _pickNodeExe, this.pickFolder = _pickFolder});
}

/// The sentence for a refused choice, from the engine's reason slug.
String laneSettingRefusal(String reason) => switch (reason) {
      'path_not_absolute' => 'Choose a full path, starting with a drive.',
      'not_a_node_executable' => 'Choose a file named node.exe.',
      'node_too_old_or_silent' =>
        'That node.exe did not report version 20 or later.',
      'local_model_root_missing' => 'That folder does not exist.',
      'local_model_root_protected' =>
        'Choose a folder outside the Flywheel home and your home folder.',
      '' => 'The engine did not keep the choice.',
      _ => 'The engine did not keep the choice ($reason).',
    };

class LaneSetupList extends StatefulWidget {
  final GatewayClient client;
  final Lane lane;
  final LaneSetupPickers pickers;

  /// Called after a choice the engine kept, so the caller can check again.
  final VoidCallback? onChanged;
  const LaneSetupList({
    super.key,
    required this.client,
    required this.lane,
    this.pickers = const LaneSetupPickers(),
    this.onChanged,
  });

  @override
  State<LaneSetupList> createState() => _LaneSetupListState();
}

class _LaneSetupListState extends State<LaneSetupList> {
  late List<LaneSetupItem> _items = widget.lane.setup;
  String? _note;
  bool _busy = false;
  var _request = 0;

  @override
  void didUpdateWidget(LaneSetupList old) {
    super.didUpdateWidget(old);
    if (!identical(old.lane, widget.lane)) _items = widget.lane.setup;
  }

  Future<void> _choose(String action, String route, bool folder) async {
    if (_busy) return;
    final picked = await (folder
        ? widget.pickers.pickFolder()
        : widget.pickers.pickNode());
    if (picked == null || picked.isEmpty || !mounted) return;
    setState(() {
      _busy = true;
      _note = null;
    });
    try {
      await _grantAndSend(action, route, picked);
    } catch (e) {
      if (mounted) setState(() => _note = 'The choice was not sent: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _grantAndSend(String action, String route, String path) async {
    final operation = GatewayOperation.exact(
        action: action,
        operation: {'path': path},
        clientRequestId: 'lane-setup-${++_request}');
    final outcome =
        await authorizeGatewayOperationDetailed<({int status, Object? body})>(
            context,
            operation,
            (body) => widget.client.postLaneAnswer(route, body,
                timeout: const Duration(seconds: 30)),
            currentOperation: () => operation);
    if (!mounted) return;
    final answer = outcome.value;
    if (answer == null) {
      final failure = outcome.failure;
      setState(() => _note = failure == null
          ? 'The choice was not approved.'
          : '${failure.code}: ${failure.message}');
      return;
    }
    final body = answer.body;
    if (answer.status != 200) {
      final reason = body is Map ? '${body['reason'] ?? ''}' : '';
      setState(() => _note = laneSettingRefusal(reason));
      return;
    }
    await _reload();
    widget.onChanged?.call();
  }

  Future<void> _reload() async {
    final body = await widget.client.laneSetup(widget.lane.name);
    final raw = body['items'];
    if (!mounted || raw is! List) return;
    setState(() => _items = [
          for (final item in raw)
            if (LaneSetupItem.tryParse(item) case final parsed?) parsed
        ]);
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    if (_items.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('setup'),
      for (final item in _items) _row(t, item),
      if (_note != null) HonestNull(_note!),
    ]);
  }

  Widget _row(FwTokens t, LaneSetupItem item) {
    final action = _actionFor(item);
    return Padding(
      padding: const EdgeInsets.only(top: FwLayout.s2),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        VerdictPill(item.met ? 'met' : 'needed',
            status: item.met ? 'verified' : 'drift'),
        const SizedBox(width: FwLayout.s2),
        Expanded(
          child: Text(
              item.copy.isEmpty ? item.title : '${item.title}. ${item.copy}',
              style: TextStyle(fontSize: 12.5, color: t.inkSoft, height: 1.4)),
        ),
        if (action != null) ...[const SizedBox(width: FwLayout.s2), action],
      ]),
    );
  }

  Widget? _actionFor(LaneSetupItem item) {
    final (label, run) = switch (item.id) {
      'node' => (
          'Choose node.exe',
          () => _choose('settings.node_path', nodePathRoute, false)
        ),
      'project_folder' => (
          'Choose folder',
          () => _choose('lane.root', localModelRootRoute, true)
        ),
      _ => ('', null),
    };
    if (run == null) return null;
    return OutlinedButton(onPressed: _busy ? null : run, child: Text(label));
  }
}
