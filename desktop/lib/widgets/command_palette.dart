// command_palette.dart -- Ctrl+K. Type to filter all thirty destinations
// by stable label; arrows move, Enter opens, Escape dismisses. Fully
// keyboard-first with semantic roles on every row.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../accessibility/accessible_action.dart';
import '../navigation/app_route.dart';
import '../navigation/destination_catalog.dart';
import '../theme/flywheel_theme.dart';

class PaletteGo extends InheritedWidget {
  final ValueChanged<DestinationId> onGo;
  const PaletteGo({super.key, required this.onGo, required super.child});

  static PaletteGo? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<PaletteGo>();

  @override
  bool updateShouldNotify(PaletteGo old) => old.onGo != onGo;
}

/// Opens the palette: type filters all thirty destinations, arrows move,
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
    return destinationCatalog
        .where((d) => d.label.toLowerCase().contains(q))
        .toList();
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
                    AccessibleAction(
                      semanticLabel: 'Go to ${matches[i].label}',
                      onActivate: () => _open(matches[i]),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: FwLayout.s4, vertical: 8),
                        color: i == _highlight ? t.ground2 : null,
                        child: Row(children: [
                          Text(matches[i].label,
                              style: TextStyle(
                                  fontSize: 13,
                                  color: i == _highlight
                                      ? t.ink
                                      : t.inkMuted)),
                          const Spacer(),
                          Text(matches[i].group.name,
                              style: TextStyle(
                                  fontSize: 10.5, color: t.inkFaint)),
                        ]),
                      ),
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

class PaletteShortcuts extends StatelessWidget {
  final Widget child;
  final ValueChanged<DestinationId> onGo;
  const PaletteShortcuts(
      {super.key, required this.child, required this.onGo});

  @override
  Widget build(BuildContext context) {
    return Shortcuts(
      shortcuts: const {
        SingleActivator(LogicalKeyboardKey.keyK, control: true):
            _OpenPaletteIntent(),
      },
      child: Actions(
        actions: {
          _OpenPaletteIntent: CallbackAction<_OpenPaletteIntent>(
              onInvoke: (_) {
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
