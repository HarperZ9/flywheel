import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'chat_code_card.dart';
import 'chat_navigation_types.dart';
import 'chat_source_span.dart';

class ChatMarkdownSourceAnchor {
  final BuildContext context;
  final double fraction;
  const ChatMarkdownSourceAnchor(this.context, this.fraction);
}

class ChatMarkdownBody extends StatefulWidget {
  final String text;
  final bool streaming;
  final ValueChanged<String>? onOpenUrl;
  final ValueChanged<ChatNavTarget>? onOpenLocalTarget;

  const ChatMarkdownBody({
    super.key,
    required this.text,
    this.streaming = false,
    this.onOpenUrl,
    this.onOpenLocalTarget,
  });

  @override
  State<ChatMarkdownBody> createState() => ChatMarkdownBodyState();
}

class ChatMarkdownBodyState extends State<ChatMarkdownBody> {
  final _keys = <String, GlobalKey>{};
  var _anchors = <_SourceAnchor>[];

  ChatMarkdownSourceAnchor? sourceAnchorForOffset(int offset) {
    if (_anchors.isEmpty) return null;
    _SourceAnchor? chosen;
    for (final anchor in _anchors) {
      if (offset >= anchor.span.start && offset <= anchor.span.end) {
        chosen = anchor;
        break;
      }
      if (anchor.span.start <= offset) chosen = anchor;
    }
    chosen ??= _anchors.first;
    final context = chosen.key.currentContext;
    if (context == null) return null;
    return ChatMarkdownSourceAnchor(context, chosen.span.fractionFor(offset));
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    if (widget.text.isEmpty && widget.streaming) {
      return Text('…', style: fwMono(t, size: 14, color: t.inkFaint));
    }
    final spans = chatSourceSpans(widget.text);
    _anchors = [
      for (final span in spans) _SourceAnchor(span, _keyFor(span)),
    ];
    _pruneKeys(_anchors.map((anchor) => anchor.id).toSet());
    if (spans.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: _renderSpans(spans),
    );
  }

  List<Widget> _renderSpans(List<ChatSourceSpan> spans) {
    final children = <Widget>[];
    var linkIndex = 0;
    for (final (index, span) in spans.indexed) {
      final text = span.text +
          (widget.streaming && index == spans.length - 1 ? '▍' : '');
      Widget child;
      if (span.code) {
        child = ChatCodeCard(code: text);
      } else if (span.blank) {
        child = const SizedBox(height: 8);
      } else if (span.headingLevel != null) {
        child = _Heading(level: span.headingLevel!, text: chatHeadingText(span));
      } else {
        child = _MarkdownLine(
          text: text,
          firstLinkIndex: linkIndex,
          onOpenUrl: widget.onOpenUrl,
          onOpenLocalTarget: widget.onOpenLocalTarget,
        );
        linkIndex += _countLinks(span.text);
      }
      children.add(KeyedSubtree(key: _keyFor(span), child: child));
    }
    return children;
  }

  GlobalKey _keyFor(ChatSourceSpan span) =>
      _keys.putIfAbsent(_anchorId(span), GlobalKey.new);
  String _anchorId(ChatSourceSpan span) => '${span.start}:${span.end}';

  void _pruneKeys(Set<String> live) =>
      _keys.removeWhere((id, _) => !live.contains(id));
}

class _SourceAnchor {
  final ChatSourceSpan span;
  final GlobalKey key;
  const _SourceAnchor(this.span, this.key);
  String get id => '${span.start}:${span.end}';
}

class _Heading extends StatelessWidget {
  final int level;
  final String text;
  const _Heading({required this.level, required this.text});
  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final size = switch (level) { 1 => 18.0, 2 => 16.5, 3 => 15.5, _ => 14.5 };
    return Padding(
      padding: const EdgeInsets.only(top: 10, bottom: 3),
      child: SelectableText(
        text,
        style: TextStyle(
          fontSize: size,
          height: 1.25,
          fontWeight: FontWeight.w700,
          color: t.ink,
        ),
      ),
    );
  }
}

class _MarkdownLine extends StatelessWidget {
  final String text;
  final int firstLinkIndex;
  final ValueChanged<String>? onOpenUrl;
  final ValueChanged<ChatNavTarget>? onOpenLocalTarget;

  const _MarkdownLine({
    required this.text,
    required this.firstLinkIndex,
    this.onOpenUrl,
    this.onOpenLocalTarget,
  });
  @override
  Widget build(BuildContext context) {
    final chunks = _parseChunks(text);
    var seenLinks = 0;
    return Padding(
      padding: const EdgeInsets.only(bottom: 3),
      child: Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [
        for (final chunk in chunks)
          chunk.url == null
              ? SelectableText(
                  chunk.text,
                  style: TextStyle(
                      fontSize: 14, height: 1.5, color: context.fw.inkSoft),
                )
              : _LinkButton(
                  index: firstLinkIndex + seenLinks++,
                  label: chunk.text,
                  url: chunk.url!,
                  onOpenUrl: onOpenUrl,
                  onOpenLocalTarget: onOpenLocalTarget,
                ),
      ]),
    );
  }
}

class _LinkButton extends StatelessWidget {
  final int index;
  final String label;
  final String url;
  final ValueChanged<String>? onOpenUrl;
  final ValueChanged<ChatNavTarget>? onOpenLocalTarget;

  const _LinkButton({
    required this.index,
    required this.label,
    required this.url,
    this.onOpenUrl,
    this.onOpenLocalTarget,
  });
  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final target = ChatNavTarget.tryParseLocalUri(url);
    final uri = Uri.tryParse(url);
    final external = uri != null && (uri.scheme == 'http' || uri.scheme == 'https');
    if (target == null && !external) {
      return SelectableText(label,
          style: TextStyle(fontSize: 14, height: 1.5, color: t.inkSoft));
    }
    return TextButton(
      key: ValueKey('chat-markdown-link-$index'),
      onPressed: () {
        if (target != null) {
          onOpenLocalTarget?.call(target);
        } else {
          onOpenUrl?.call(url);
        }
      },
      style: TextButton.styleFrom(
        minimumSize: const Size(24, 28),
        padding: const EdgeInsets.symmetric(horizontal: 2),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 14,
          height: 1.35,
          color: t.drift,
          decoration: TextDecoration.underline,
          decorationColor: t.drift.withValues(alpha: 0.45),
        ),
      ),
    );
  }
}

List<_Chunk> _parseChunks(String text) {
  final chunks = <_Chunk>[];
  final markdown = RegExp(r'\[([^\]\n]+)\]\(([^\s)]+)\)');
  final bare = RegExp(r'https?://[^\s<>)\]]+');
  var cursor = 0;
  while (cursor < text.length) {
    final markdownMatch = markdown.matchAsPrefix(text, cursor);
    if (markdownMatch != null) {
      chunks.add(_Chunk(markdownMatch.group(1)!,
          url: _cleanUrl(markdownMatch.group(2)!)));
      cursor = markdownMatch.end;
      continue;
    }
    final bareMatch = bare.matchAsPrefix(text, cursor);
    if (bareMatch != null) {
      final url = _cleanUrl(bareMatch.group(0)!);
      chunks.add(_Chunk(url, url: url));
      cursor = bareMatch.end;
      continue;
    }
    final nextMarkdown = _firstMatchAfter(markdown, text, cursor);
    final nextBare = _firstMatchAfter(bare, text, cursor);
    final next = [
      if (nextMarkdown != null) nextMarkdown.start,
      if (nextBare != null) nextBare.start,
    ].fold<int?>(null, (best, value) => best == null || value < best ? value : best);
    final end = next ?? text.length;
    chunks.add(_Chunk(text.substring(cursor, end)));
    cursor = end;
  }
  return chunks.where((chunk) => chunk.text.isNotEmpty).toList();
}

int _countLinks(String line) =>
    _parseChunks(line).where((chunk) => chunk.url != null).length;
String _cleanUrl(String value) => value.replaceFirst(RegExp(r'[.,;:]+$'), '');
RegExpMatch? _firstMatchAfter(RegExp pattern, String text, int start) {
  for (final match in pattern.allMatches(text, start)) {
    return match;
  }
  return null;
}

final class _Chunk {
  const _Chunk(this.text, {this.url});
  final String text;
  final String? url;
}
