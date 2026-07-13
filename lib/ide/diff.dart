// diff.dart — a native line diff for the Code lane: what the agent changed,
// shown as evidence rather than asserted. LCS-based, capped honestly: a
// pair too large to diff says so instead of stalling the pane.

const int _maxDiffLines = 1500;

enum DiffKind { same, add, del }

class DiffLine {
  final DiffKind kind;
  final String text;
  const DiffLine(this.kind, this.text);
}

class FileDiff {
  final String path;
  final List<DiffLine> lines;
  final String? note;
  const FileDiff(this.path, this.lines, {this.note});

  int get added => lines.where((l) => l.kind == DiffKind.add).length;
  int get removed => lines.where((l) => l.kind == DiffKind.del).length;
}

/// Diff two file contents line-wise. Unchanged runs longer than three lines
/// collapse to a context marker so the changes carry the view.
FileDiff diffFiles(String path, String before, String after) {
  final a = before.split('\n');
  final b = after.split('\n');
  if (a.length > _maxDiffLines || b.length > _maxDiffLines) {
    return FileDiff(path, const [],
        note: 'file too large to diff here; the change is on disk');
  }
  final ops = _diffOps(a, b);
  final out = <DiffLine>[];
  var sameRun = <String>[];

  void flushSame() {
    if (sameRun.length <= 6) {
      out.addAll(sameRun.map((s) => DiffLine(DiffKind.same, s)));
    } else {
      out.addAll(sameRun.take(3).map((s) => DiffLine(DiffKind.same, s)));
      out.add(DiffLine(DiffKind.same, '··· ${sameRun.length - 6} unchanged lines ···'));
      out.addAll(
          sameRun.skip(sameRun.length - 3).map((s) => DiffLine(DiffKind.same, s)));
    }
    sameRun = [];
  }

  for (final op in ops) {
    if (op.kind == DiffKind.same) {
      sameRun.add(op.text);
    } else {
      flushSame();
      out.add(op);
    }
  }
  flushSame();
  return FileDiff(path, out);
}

/// LCS dynamic program over lines. Sizes are capped by the caller.
List<DiffLine> _diffOps(List<String> a, List<String> b) {
  final n = a.length, m = b.length;
  // lcs[i][j] = LCS length of a[i:], b[j:]
  final lcs = List.generate(n + 1, (_) => List<int>.filled(m + 1, 0));
  for (var i = n - 1; i >= 0; i--) {
    for (var j = m - 1; j >= 0; j--) {
      lcs[i][j] = a[i] == b[j]
          ? lcs[i + 1][j + 1] + 1
          : (lcs[i + 1][j] >= lcs[i][j + 1] ? lcs[i + 1][j] : lcs[i][j + 1]);
    }
  }
  final out = <DiffLine>[];
  var i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] == b[j]) {
      out.add(DiffLine(DiffKind.same, a[i]));
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      out.add(DiffLine(DiffKind.del, a[i]));
      i++;
    } else {
      out.add(DiffLine(DiffKind.add, b[j]));
      j++;
    }
  }
  while (i < n) {
    out.add(DiffLine(DiffKind.del, a[i++]));
  }
  while (j < m) {
    out.add(DiffLine(DiffKind.add, b[j++]));
  }
  return out;
}
