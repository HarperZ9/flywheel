// recovery_center.dart -- one typed surface over everything recoverable:
// unsent prompts, dirty buffers, pending journey drafts, interrupted
// operations. Reached from the shell footer, never a thirty-first
// destination. Restore offers only actions the item advertises; nothing
// deletes itself and server evidence never changes from here.
import 'dart:async';

import 'package:flutter/material.dart';

import '../models/recovery_item.dart';
import '../services/recovery_catalog.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/recovery_item_card.dart';

class RecoveryCenter extends StatefulWidget {
  final RecoveryCatalog catalog;
  const RecoveryCenter({super.key, required this.catalog});

  @override
  State<RecoveryCenter> createState() => _RecoveryCenterState();
}

class _RecoveryCenterState extends State<RecoveryCenter> {
  List<RecoveryItem> _items = [];
  bool _loading = true;
  String? _note;

  @override
  void initState() {
    super.initState();
    unawaited(_refresh());
  }

  Future<void> _refresh() async {
    final items = await widget.catalog.refresh();
    if (!mounted) return;
    setState(() {
      _items = items;
      _loading = false;
    });
  }

  Future<void> _perform(RecoveryItem item, RecoveryActionSpec action) async {
    final ok = await widget.catalog.perform(item, action.id);
    if (!mounted) return;
    setState(() => _note = ok
        ? '${action.label}: done.'
        : '${action.label}: the action could not be completed; the item '
            'stays until its state allows it.');
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return ViewScroll(
      children: [
        SectionHeader('Recovery',
            kicker: 'nothing here deletes itself',
            trailing: OutlinedButton(
                onPressed: _loading ? null : _refresh,
                child: Text(_loading ? 'Reading…' : 'Re-read'))),
        const SizedBox(height: FwLayout.s4),
        if (_note != null) ...[
          HonestNull(_note!),
          const SizedBox(height: FwLayout.s4),
        ],
        if (_loading)
          const Center(child: CircularProgressIndicator(strokeWidth: 2))
        else if (_items.isEmpty)
          const HonestNull(
              'Nothing is waiting to be recovered. Drafts, buffers, and '
              'operations appear here only when they were interrupted.')
        else
          for (final item in _items)
            RecoveryItemCard(
                item: item,
                onAction: (action) => unawaited(_perform(item, action))),
        const SizedBox(height: FwLayout.s5),
        Text(
            'Recovery reads device-local journals only. Journey evidence '
            'and receipts change only through newly admitted server '
            'events.',
            style: fwMono(t, size: 10.5, color: t.inkFaint)),
      ],
    );
  }
}
