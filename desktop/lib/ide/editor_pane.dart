// editor_pane.dart — the editing surface: line numbers beside a highlighted
// Conso field, Ctrl+S to save, read-only fallback for large or binary
// files. The pane owns nothing but rendering; the Code view owns the open
// files and their controllers.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import 'highlighter.dart';

class OpenFile {
  final String path;
  final CodeEditingController controller;
  final bool readOnly;
  final String? note;
  bool dirty = false;

  OpenFile(
      {required this.path,
      required this.controller,
      this.readOnly = false,
      this.note});

  String get name => path.split(RegExp(r'[\\/]')).last;
}

class EditorPane extends StatelessWidget {
  final OpenFile file;
  final VoidCallback onSave;
  final VoidCallback onChanged;
  final VoidCallback? onDefinition;
  final VoidCallback? onReferences;
  const EditorPane(
      {super.key,
      required this.file,
      required this.onSave,
      required this.onChanged,
      this.onDefinition,
      this.onReferences});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final lineCount = '\n'.allMatches(file.controller.text).length + 1;
    final numberWidth = (lineCount.toString().length * 8.0) + 18;
    final editorStyle = fwMono(t, size: 13).copyWith(height: 1.5);
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): onSave,
        if (onDefinition != null)
          const SingleActivator(LogicalKeyboardKey.f12): onDefinition!,
        if (onReferences != null)
          const SingleActivator(LogicalKeyboardKey.f12, shift: true):
              onReferences!,
      },
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (file.note != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(
                  FwLayout.s4, FwLayout.s2, FwLayout.s4, 0),
              child: HonestNull(file.note!),
            ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(vertical: FwLayout.s3),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: numberWidth,
                    padding: const EdgeInsets.only(right: 10, top: 1),
                    child: Text(
                      List.generate(lineCount, (i) => '${i + 1}').join('\n'),
                      textAlign: TextAlign.right,
                      style: fwMono(t, size: 13, color: t.inkFaint)
                          .copyWith(height: 1.5),
                    ),
                  ),
                  Container(width: 1, color: t.hairline),
                  const SizedBox(width: 10),
                  Expanded(
                    child: TextField(
                      controller: file.controller,
                      readOnly: file.readOnly,
                      maxLines: null,
                      style: editorStyle,
                      cursorColor: t.drift,
                      decoration: const InputDecoration(
                        isDense: true,
                        border: InputBorder.none,
                        enabledBorder: InputBorder.none,
                        focusedBorder: InputBorder.none,
                        filled: false,
                        contentPadding: EdgeInsets.zero,
                      ),
                      onChanged: (_) => onChanged(),
                    ),
                  ),
                  const SizedBox(width: FwLayout.s4),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
