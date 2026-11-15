"""Schema-tolerant proof contract indexing."""

from .indexer import ProofRow, format_table, load_rows, summarize_contract

__all__ = [
    "ProofRow",
    "format_table",
    "load_rows",
    "summarize_contract",
]
__version__ = "0.2.0"

