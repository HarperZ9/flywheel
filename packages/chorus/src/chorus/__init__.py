"""chorus: read a comment section as ranked, re-checkable themes.

Turns a corpus of comments and threads into a weighted, clustered, re-checkable
reading of the discourse. Sentiment is a weight and a signal here, never an
accept gate. Stdlib only; deterministic; every digest carries a receipt.
"""
from chorus.item import DiscourseItem, normalize

__version__ = "0.3.2"
__all__ = ["DiscourseItem", "normalize"]
