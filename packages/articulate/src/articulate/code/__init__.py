"""articulate.code -- static checks on code changes, starting with test diffs.

`analyze(changes)` reports whether a change made its Python tests check less
(deleted or weakened assertions, widened tolerances, new skips) and whether the
tests it adds or edits can fail at all (`assert True`, self-comparison, mock-only
checks). Report-only, standard library only, and it imports nothing from the
frozen prose-detector closure.
"""
from .report import DOES_NOT_PROVE, SCHEMA, FileChange, analyze, render_text

__all__ = ["analyze", "FileChange", "render_text", "SCHEMA", "DOES_NOT_PROVE"]
