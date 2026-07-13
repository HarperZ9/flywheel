// file_tree.dart — the workspace tree: lazy directory expansion, mono
// labels, the open file marked with the drift bar. Reads through
// workspace.listDir so the ignore rules live in one place.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'workspace.dart';

class FileTree extends StatefulWidget {
  final String root;
  final String? activePath;
  final ValueChanged<String> onOpen;
  const FileTree(
      {super.key,
      required this.root,
      required this.onOpen,
      this.activePath});

  @override
  State<FileTree> createState() => _FileTreeState();
}

class _FileTreeState extends State<FileTree> {
  final Set<String> _expanded = {};
  final Map<String, List<WorkspaceEntry>> _cache = {};
  String? _error;

  List<WorkspaceEntry> _entries(String path) {
    return _cache.putIfAbsent(path, () {
      try {
        return listDir(path);
      } catch (e) {
        _error = '$e';
        return const [];
      }
    });
  }

  void _refresh() => setState(() {
        _cache.clear();
        _error = null;
      });

  @override
  void didUpdateWidget(FileTree old) {
    super.didUpdateWidget(old);
    if (old.root != widget.root) {
      _expanded.clear();
      _cache.clear();
      _error = null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final rows = <Widget>[];
    _buildRows(rows, widget.root, 0);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(
              FwLayout.s3, FwLayout.s3, FwLayout.s2, FwLayout.s2),
          child: Row(
            children: [
              Expanded(
                child: Text(widget.root.split(RegExp(r'[\\/]')).last,
                    overflow: TextOverflow.ellipsis,
                    style: fwMono(t, size: 11.5, weight: FontWeight.w600)),
              ),
              MouseRegion(
                cursor: SystemMouseCursors.click,
                child: GestureDetector(
                  onTap: _refresh,
                  child: Icon(Icons.refresh, size: 13, color: t.inkFaint),
                ),
              ),
            ],
          ),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.all(FwLayout.s3),
            child: Text(_error!,
                style: TextStyle(fontSize: 11, color: t.drift)),
          ),
        Expanded(
          child: ListView(padding: EdgeInsets.zero, children: rows),
        ),
      ],
    );
  }

  void _buildRows(List<Widget> rows, String dir, int depth) {
    for (final e in _entries(dir)) {
      rows.add(_row(e, depth));
      if (e.isDir && _expanded.contains(e.path)) {
        _buildRows(rows, e.path, depth + 1);
      }
    }
  }

  Widget _row(WorkspaceEntry e, int depth) {
    final t = context.fw;
    final active = e.path == widget.activePath;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: () {
          if (e.isDir) {
            setState(() {
              _expanded.contains(e.path)
                  ? _expanded.remove(e.path)
                  : _expanded.add(e.path);
            });
          } else {
            widget.onOpen(e.path);
          }
        },
        behavior: HitTestBehavior.opaque,
        child: Container(
          padding: EdgeInsets.only(
              left: FwLayout.s3 + depth * 14.0,
              top: 3,
              bottom: 3,
              right: FwLayout.s2),
          color: active ? t.panel : Colors.transparent,
          child: Row(
            children: [
              Icon(
                e.isDir
                    ? (_expanded.contains(e.path)
                        ? Icons.folder_open_outlined
                        : Icons.folder_outlined)
                    : Icons.description_outlined,
                size: 13,
                color: e.isDir ? t.inkMuted : t.inkFaint,
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(e.name,
                    overflow: TextOverflow.ellipsis,
                    style: fwMono(t,
                        size: 11.5,
                        color: active ? t.ink : t.inkSoft,
                        weight: active ? FontWeight.w600 : FontWeight.w400)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
