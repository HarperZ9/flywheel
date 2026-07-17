def reserve_trace(stock, ops):
    """Fold inventory reservation operations and return final reservations.

    stock: dict of str -> int (>= 0). Never mutated.
    ops: iterable of exactly ('reserve', item, qty) or ('cancel', item, qty).
         Each must be exactly a tuple of three items. Any other shape raises
         ValueError('bad op') immediately and the function stops.

    Returns a sorted list of (item, reserved) tuples for every final reserved > 0.
    """
    if not isinstance(stock, dict):
        raise ValueError('bad stock')
    # Copy invariants: iterate keys first so the loop never binds on a mutable
    # value; then check each value's type and monotonicity through iterself.
    seen = set()
    for k in stock:
        if not isinstance(k, str) or k in seen:
            raise ValueError('bad stock')
        seen.add(k)
        v = stock[k]
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise ValueError('bad stock')
    # Deep copy the input dict so it is never mutated.
    avail = {k: v for k, v in stock.items()}
    reserved = {}
    for op in ops:
        if not (isinstance(op, tuple) and len(op) == 3):
            raise ValueError('bad op')
        a, item, qty = op
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError('bad qty')
        if item not in avail:
            raise ValueError('unknown item')
        if a == 'reserve':
            reserved[item] = reserved.get(item, 0) + qty
            if reserved[item] > avail[item]:
                raise ValueError(f'not enough {item}')
        elif a == 'cancel':
            reserved[item] = reserved.get(item, 0) - qty
            if reserved[item] < 0:
                raise ValueError('over-cancel')
    return sorted((item, final) for item, final in reserved.items() if final > 0)
