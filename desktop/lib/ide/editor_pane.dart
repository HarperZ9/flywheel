// editor_pane.dart — the editing surface: line numbers beside a highlighted
// Conso field, Ctrl+S to save, read-only fallback for large or binary
// files. The pane owns nothing but rendering; the Code view owns the open
// files and their controllers.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import 'code_buffer_session.dart';

typedef EditorAttachment = ({String relativePath, String? selection});
typedef EditorAttachmentSupplier = EditorAttachment? Function();
final _incompletePercent = RegExp(r'%(?![0-9A-Fa-f]{2})');

EditorAttachment? editorAttachmentOf(OpenFile? file) {
  if (file == null) return null;
  final selection = file.controller.selection;
  return (
    relativePath: file.relativePath,
    selection: !selection.isValid || selection.isCollapsed
        ? null
        : selection.textInside(file.controller.text),
  );
}

bool isClosedRelativeAttachmentPath(String value) {
  if (value.trim().isEmpty || value.length > 1024) return false;
  var form = value;
  for (var decoding = 0; decoding <= 3; decoding++) {
    if (!_isRelativePathForm(form)) return false;
    if (decoding == 3) return true;
    try {
      final escaped = form.replaceAllMapped(_incompletePercent, (_) => '%25');
      final decoded = Uri.decodeComponent(escaped);
      if (decoded == form) return true;
      form = decoded;
    } on FormatException {
      return false;
    }
  }
  return true;
}

Map<String, Object?>? closedEditorAttachment(
    bool enabled,
    EditorAttachmentSupplier? supplier,
    String? relativePath,
    String? selection) {
  if (!enabled) return null;
  final attachment = supplier != null
      ? supplier()
      : relativePath == null
          ? null
          : (relativePath: relativePath, selection: selection);
  if (attachment == null) return null;
  if (!isClosedRelativeAttachmentPath(attachment.relativePath)) {
    throw const FormatException();
  }
  return {
    'relative_path': attachment.relativePath,
    if (attachment.selection case final String value)
      if (value.isNotEmpty) 'selection': value,
  };
}

bool _isRelativePathForm(String value) =>
    !value.startsWith('/') &&
    !value.startsWith(r'\') &&
    !value.contains(':') &&
    !value.contains(r'\') &&
    value
        .split('/')
        .every((part) => part.isNotEmpty && part != '.' && part != '..');

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
          _editor(t, lineCount, numberWidth, editorStyle),
        ],
      ),
    );
  }

  Widget _editor(
          FwTokens t, int lineCount, double numberWidth, TextStyle style) =>
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
                  style: style,
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
      );
}
