final class ChatSourceSpan {
  final int start;
  final int end;
  final String text;
  final bool code;
  final int? headingLevel;

  const ChatSourceSpan({
    required this.start,
    required this.end,
    required this.text,
    this.code = false,
    this.headingLevel,
  });

  bool get blank => text.trim().isEmpty;

  double fractionFor(int offset) {
    final span = end - start;
    if (span <= 0) return 0;
    return ((offset - start) / span).clamp(0.0, 1.0);
  }
}

final _headingPattern = RegExp(r'^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$');
final _fencePattern = RegExp(r'^ {0,3}(```+|~~~+)');

List<ChatSourceSpan> chatSourceSpans(String text) {
  final spans = <ChatSourceSpan>[];
  final code = StringBuffer();
  var inCode = false;
  var codeStart = 0;
  var cursor = 0;
  _FenceRun? openFence;

  void flushCode(int end) {
    spans.add(ChatSourceSpan(
      start: codeStart,
      end: end,
      text: code.toString().trimRight(),
      code: true,
    ));
    code.clear();
  }

  while (cursor < text.length) {
    final newline = text.indexOf('\n', cursor);
    final contentEnd = newline == -1 ? text.length : newline;
    final next = newline == -1 ? text.length : newline + 1;
    final line = text.substring(cursor, contentEnd);
    final fence = _readFence(line);
    if (inCode) {
      if (_closesFence(openFence!, line)) {
        flushCode(cursor);
        inCode = false;
        openFence = null;
      } else {
        code.writeln(line);
      }
    } else if (fence != null) {
      codeStart = next;
      inCode = true;
      openFence = fence;
    } else {
      final heading = _headingPattern.firstMatch(line);
      spans.add(ChatSourceSpan(
        start: cursor,
        end: contentEnd,
        text: line,
        headingLevel: heading?.group(1)!.length,
      ));
    }
    cursor = next;
  }
  if (inCode) flushCode(text.length);
  return spans;
}

String chatHeadingText(ChatSourceSpan span) {
  final match = _headingPattern.firstMatch(span.text);
  return match == null ? span.text.trim() : match.group(2)!.trim();
}

_FenceRun? _readFence(String line) {
  final match = _fencePattern.firstMatch(line);
  if (match == null) return null;
  final marker = match.group(1)!;
  return _FenceRun(marker[0], marker.length);
}

bool _closesFence(_FenceRun openFence, String line) {
  final match = _fencePattern.firstMatch(line);
  if (match == null) return false;
  final marker = match.group(1)!;
  if (marker[0] != openFence.character) return false;
  if (marker.length < openFence.length) return false;
  return line.substring(match.end).trim().isEmpty;
}

final class _FenceRun {
  final String character;
  final int length;

  const _FenceRun(this.character, this.length);
}
