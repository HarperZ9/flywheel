def reserve_trace(stock, ops):
    # Copy stock without mutating input dict; also validate all values are ints >= 0.
    _stock = {}
    for k, v in stock.items():
        if not isinstance(k, str):
            raise ValueError('bad stock')
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise ValueError('bad stock')
        _stock[k] = v
    reserved = {k: 0 for k in _stock}

    for op in ops:
        if len(op) != 3 or (op[0] not in ('reserve', 'cancel')):
            raise ValueError('bad op')
        action, item, qty = op

        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError('bad qty')
        if item not in _stock:
            raise ValueError('unknown item')

        av = _stock[item] - reserved.get(item, 0)
        if action == 'reserve':
            if qty > av:
                raise ValueError(f'not enough {item}')
            reserved[item] += qty
        else:           # cancel
            if qty > reserved.get(item, 0):
                raise ValueError('over-cancel')
            reserved[item] -= qty

    # Collect only items with positive remaining reservation.
    out = [(k, v) for k, v in sorted(reserved.items()) if v > 0]
    return out
