"""proof_relations.py -- the arithmetic a contract states, rendered for a prover.

A contract can say what has to hold between its fields: that the total is the
sum of its parts, that a dose is not negative, that a filing date falls before
a deadline. Those statements are the part of a checked answer that needs no
authority at all. They are arithmetic, and arithmetic is what a proof assistant
settles by computation rather than by agreement.

A relation is written the way a person would write it:

    total = subtotal + tax
    0 <= dose
    fee <= 2 * base

It is parsed with `ast` and never evaluated. Only names, integer and decimal
literals, addition, subtraction, negation, multiplication by a constant, and
the six comparisons survive the walk. Anything else is refused at emit time,
because a relation that quietly means something other than what it says would
produce a proof of the wrong statement.

Every quantity is carried in the same fixed-point scale, so cents never get
added to dollars. A bare literal in a sum or a comparison is a quantity and is
scaled with everything else. A literal multiplying a quantity is a plain factor
and is not, since doubling a value does not double its units.
"""
from __future__ import annotations

import ast
import re
from decimal import Decimal, InvalidOperation

# Lean's own spellings. `=` is definitional equality on Int, and the four
# order relations are decidable, so every one of these closes by `decide`.
# A person writing a contract writes `total = subtotal + tax`, which Python
# reads as an assignment. One `=` that is not part of `==`, `!=`, `<=` or `>=`
# becomes `==` before the walk, so the natural spelling is the accepted one.
SINGLE_EQUALS = re.compile(r"(?<![=!<>])=(?!=)")

COMPARISONS = {ast.Eq: "=", ast.NotEq: "≠", ast.Lt: "<", ast.LtE: "≤",
               ast.Gt: ">", ast.GtE: "≥"}

# Nine places is already past what any authority in the critical domains
# publishes, and it keeps a float's rounding tail from setting the scale for
# the whole file.
MAX_SCALE = 9


class RelationError(ValueError):
    """Raised on a relation this module will not turn into a claim."""


def numeric(value) -> bool:
    """A quantity, and not a bool wearing an int's clothes."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def places(value) -> int:
    """How many decimal places a value needs to be exact.

    A value that is not a finite decimal at all answers with more than any
    scale allows, so a caller that compares against MAX_SCALE rejects it
    without having to test for a NaN separately.
    """
    try:
        exponent = Decimal(str(value)).normalize().as_tuple().exponent
    except InvalidOperation:
        return MAX_SCALE + 1
    return max(0, -int(exponent)) if isinstance(exponent, int) else MAX_SCALE + 1


def fixed_point(value, scale: int) -> str | None:
    """The value as an integer in `scale`, or None if it will not fit exactly.

    None rather than a rounded number. A proof about a rounded value is a
    proof about a number nobody stated, and it would carry the same weight as
    one about the number they did.
    """
    try:
        exact = Decimal(str(value)) * (10 ** scale)
    except InvalidOperation:
        return None
    if not exact.is_finite() or exact != exact.to_integral_value():
        return None
    number = int(exact)
    return f"({number})" if number < 0 else str(number)


def scaled_literal(value, scale: int) -> str:
    """A decimal literal as an integer in the file's fixed-point scale."""
    out = fixed_point(value, scale)
    if out is None:
        raise RelationError(f"{value} needs more than {scale} decimal places")
    return out


def quantity(node: ast.AST, names: dict[str, str], scale: int) -> str:
    """One side of a relation, in the scale every field is carried in."""
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise RelationError(f"no field named {node.id!r} in the answer")
        return names[node.id]
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise RelationError(f"{node.value!r} is not a quantity")
        return scaled_literal(node.value, scale)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return f"(- {quantity(node.operand, names, scale)})"
    if isinstance(node, ast.BinOp):
        return _binop(node, names, scale)
    raise RelationError(f"{type(node).__name__} is not allowed in a relation")


def _binop(node: ast.BinOp, names: dict[str, str], scale: int) -> str:
    if isinstance(node.op, (ast.Add, ast.Sub)):
        symbol = "+" if isinstance(node.op, ast.Add) else "-"
        return (f"({quantity(node.left, names, scale)} {symbol} "
                f"{quantity(node.right, names, scale)})")
    if isinstance(node.op, ast.Mult):
        # One side has to be a plain factor. Multiplying two scaled quantities
        # would silently square the scale, and the resulting theorem would be
        # true about numbers that are not the ones the answer states.
        for factor, other in ((node.left, node.right), (node.right, node.left)):
            if isinstance(factor, ast.Constant) and not isinstance(other, ast.Constant):
                return (f"({scaled_literal(factor.value, 0)} * "
                        f"{quantity(other, names, scale)})")
        raise RelationError("multiplication needs a constant on one side")
    raise RelationError(f"{type(node.op).__name__} is not allowed in a relation")


def claims(relation: str, names: dict[str, str], scale: int) -> list[str]:
    """The Lean propositions one written relation stands for.

    A chained comparison becomes one proposition per link rather than a
    conjunction, so a file that fails to check says which link failed.

    A relation can only name fields whose names are identifiers. A field
    called `2nd payment` is reachable by every other part of the check and not
    by this one, and no rename happens here to make it reachable: a relation
    about a field the writer did not name is not the relation they wrote.
    """
    try:
        tree = ast.parse(SINGLE_EQUALS.sub("==", relation.strip()), mode="eval")
    except SyntaxError as exc:
        raise RelationError(f"cannot read {relation!r}: {exc.msg}") from exc
    node = tree.body
    if not isinstance(node, ast.Compare):
        raise RelationError(f"{relation!r} states no comparison")
    out = []
    left = node.left
    for op, right in zip(node.ops, node.comparators):
        symbol = COMPARISONS.get(type(op))
        if symbol is None:
            raise RelationError(f"{type(op).__name__} is not allowed in a relation")
        out.append(f"{quantity(left, names, scale)} {symbol} "
                   f"{quantity(right, names, scale)}")
        left = right
    return out
