import 'package:flutter/material.dart';

import '../client/bulletin_media_api.dart';

final class BulletinMediaCredentialSelection {
  final TextEditingController controller;
  List<BulletinMediaCredentialHandle> handles = const [];
  String? message;

  BulletinMediaCredentialSelection(this.controller);

  String get selectedRef => controller.text.trim();

  void apply(List<BulletinMediaCredentialHandle> rows) {
    handles = rows;
    if (rows.isEmpty) {
      controller.clear();
      message = _missingCredentialMessage;
    } else {
      if (rows.every((row) => row.credentialRef != selectedRef)) {
        controller.text = rows.first.credentialRef;
      }
      message = null;
    }
  }

  void fail() {
    handles = const [];
    controller.clear();
    message =
        'Credential handles could not be read. Open the Keys identity workflow and bind BULLETIN_AGENT_JWK if it is missing.';
  }

  void select(BulletinMediaCredentialHandle handle) {
    controller.text = handle.credentialRef;
    message = null;
  }
}

const _missingCredentialMessage =
    'No BULLETIN_AGENT_JWK credential handle is bound. Open the Keys identity workflow and bind the existing Bulletin identity before preview.';

final class BulletinMediaCredentialScope extends InheritedWidget {
  final BulletinMediaCredentialSelection selection;
  final VoidCallback onRefresh;
  final ValueChanged<BulletinMediaCredentialHandle> onSelected;

  const BulletinMediaCredentialScope({
    super.key,
    required this.selection,
    required this.onRefresh,
    required this.onSelected,
    required super.child,
  });

  static BulletinMediaCredentialScope? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<BulletinMediaCredentialScope>();

  @override
  bool updateShouldNotify(BulletinMediaCredentialScope oldWidget) => true;
}

final class BulletinMediaCredentialPicker extends StatelessWidget {
  final TextEditingController controller;
  final bool busy;

  const BulletinMediaCredentialPicker({
    super.key,
    required this.controller,
    required this.busy,
  });

  @override
  Widget build(BuildContext context) {
    final scope = BulletinMediaCredentialScope.maybeOf(context);
    final selection = scope?.selection;
    final handles = selection?.handles ?? const <BulletinMediaCredentialHandle>[];
    final byRef = {for (final handle in handles) handle.credentialRef: handle};
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      TextField(
        key: const ValueKey('bulletin-credential'),
        controller: controller,
        readOnly: true,
        decoration: const InputDecoration(
          labelText: 'Selected credential handle',
          helperText: 'Presence only; values never leave the engine.',
        ),
      ),
      const SizedBox(height: 8),
      OutlinedButton(
        key: const ValueKey('bulletin-refresh-credentials'),
        onPressed: busy ? null : scope?.onRefresh,
        child: const Text('Refresh credential handles'),
      ),
      if (handles.isEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(selection?.message ?? _missingCredentialMessage),
        ),
      RadioGroup<String>(
        groupValue: selection?.selectedRef,
        onChanged: (value) {
          if (busy) return;
          final handle = byRef[value];
          if (handle != null) scope?.onSelected(handle);
        },
        child: Column(children: [
          for (final handle in handles)
            RadioListTile<String>(
              key: ValueKey('bulletin-credential-${handle.credentialRef}'),
              value: handle.credentialRef,
              title: Text(handle.credentialName),
              subtitle: Text(handle.credentialRef),
            ),
        ]),
      ),
    ]);
  }
}
