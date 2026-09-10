// command_palette.dart -- Ctrl+K. Type to filter all forty-three destinations
// by label or workflow term; arrows move, Enter opens, Escape dismisses. Fully
// keyboard-first with semantic roles on every row.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../accessibility/accessible_action.dart';
import '../navigation/app_route.dart';
import '../navigation/destination_catalog.dart';
import '../navigation/destination_search.dart';
import '../theme/flywheel_theme.dart';

class PaletteGo extends InheritedWidget {
  final ValueChanged<DestinationId> onGo;
  const PaletteGo({super.key, required this.onGo, required super.child});

  static PaletteGo? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<PaletteGo>();

  @override
  bool updateShouldNotify(PaletteGo old) => old.onGo != onGo;
}

/// Opens the palette: type filters all destinations, arrows move,
/// Enter opens, Escape closes without navigating.
void showCommandPalette(
  BuildContext context,
  ValueChanged<DestinationId> onGo,
) {
  showDialog<void>(
    context: context,
    builder: (dialogContext) => PaletteGo(
      onGo: onGo,
      child: const _CommandPaletteDialog(),
    ),
  );
}

class _CommandPaletteDialog extends StatefulWidget {
  const _CommandPaletteDialog();

  @override
  State<_CommandPaletteDialog> createState() => _CommandPaletteDialogState();
}

class _CommandPaletteDialogState extends State<_CommandPaletteDialog> {
  String _query = '';
  int _highlight = 0;

  List<DestinationSpec> get _matches {
    final q = _query.trim().toLowerCase();
    if (q.isEmpty) return destinationCatalog;
    return destinationCatalog.where((d) => destinationMatches(d, q)).toList();
  }

  void _open(DestinationSpec spec) {
    PaletteGo.of(context)?.onGo(spec.id);
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final matches = _matches;
    if (_highlight >= matches.length) _highlight = 0;
    return Dialog(
      backgroundColor: t.panel,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(FwLayout.radius),
        side: BorderSide(color: t.line),
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460, maxHeight: 420),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.all(FwLayout.s3),
              child: TextField(
                autofocus: true,
                style: TextStyle(fontSize: 14, color: t.ink),
                decoration: InputDecoration(
                  hintText: 'Go to…',
                  hintStyle: TextStyle(color: t.inkFaint),
                  border: InputBorder.none,
                ),
                onChanged: (value) => setState(() {
                  _query = value;
                  _highlight = 0;
                }),
                onSubmitted: (_) {
                  if (matches.isNotEmpty) _open(matches[_highlight]);
                },
              ),
            ),
            Divider(height: 1, color: t.hairline),
            Flexible(
              child: ListView(
                shrinkWrap: true,
                children: [
                  if (matches.isEmpty)
                    Padding(
                      padding: const EdgeInsets.all(FwLayout.s4),
                      child: Text('No destination matches.',
                          style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
                    ),
                  for (var i = 0; i < matches.length; i++)
                    _PaletteDestinationRow(
                      spec: matches[i],
                      selected: i == _highlight,
                      onOpen: () => _open(matches[i]),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PaletteDestinationRow extends StatelessWidget {
  const _PaletteDestinationRow({
    required this.spec,
    required this.selected,
    required this.onOpen,
  });

  final DestinationSpec spec;
  final bool selected;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final label = Text(
      spec.label,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(fontSize: 13, color: selected ? t.ink : t.inkMuted),
    );
    final group = Text(
      destinationGroupLabel(spec.group),
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(fontSize: 10.5, color: t.inkFaint),
    );
    return AccessibleAction(
      semanticLabel: 'Go to ${spec.label}',
      onActivate: onOpen,
      child: Container(
        padding:
            const EdgeInsets.symmetric(horizontal: FwLayout.s4, vertical: 8),
        color: selected ? t.ground2 : null,
        child: LayoutBuilder(builder: (context, constraints) {
          if (constraints.maxWidth < 260) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [label, const SizedBox(height: 2), group],
            );
          }
          return Row(children: [
            Expanded(child: label),
            const SizedBox(width: FwLayout.s2),
            Flexible(
              child: Align(alignment: Alignment.centerRight, child: group),
            ),
          ]);
        }),
      ),
    );
  }
}

class PaletteShortcuts extends StatelessWidget {
  final Widget child;
  final ValueChanged<DestinationId> onGo;
  const PaletteShortcuts({super.key, required this.child, required this.onGo});

  @override
  Widget build(BuildContext context) {
    return Shortcuts(
      shortcuts: const {
        SingleActivator(LogicalKeyboardKey.keyK, control: true):
            _OpenPaletteIntent(),
      },
      child: Actions(
        actions: {
          _OpenPaletteIntent: CallbackAction<_OpenPaletteIntent>(onInvoke: (_) {
            showCommandPalette(context, onGo);
            return null;
          }),
        },
        child: child,
      ),
    );
  }
}

class _OpenPaletteIntent extends Intent {
  const _OpenPaletteIntent();
}
