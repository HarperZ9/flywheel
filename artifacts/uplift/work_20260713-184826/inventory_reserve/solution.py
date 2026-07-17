def reserve_trace(stock, ops):
    if not all(isinstance(v, int) and v >= 0 for v in stock.values()):
        raise ValueError('bad stock')

    for op in ops:
        if len(op) != 3 or op[0] not in ['reserve', 'cancel'] or not isinstance(op[2], int) or op[2] <= 0:
            raise ValueError('bad op')
        
        item = op[1]
        qty = op[2]

        if item not in stock or stock[item] < 0:
            raise ValueError('unknown item')

        if op[0] == 'reserve':
            if qty > stock[item]:
                raise ValueError('not enough ' + item)
            available = stock[item] - stock.get(item + '_res', 0)
            if qty > available:
                raise ValueError('not enough ' + item)

            if item in stock:
                stock[item + '_res'] = (stock.get(item + '_res', 0) + qty)
            else:
                stock[item + '_res'] = qty

        elif op[0] == 'cancel':
            reserved_count = stock.get(item + '_res', 0)
            if qty > reserved_count:
                raise ValueError('over-cancel')
            
            stock[item + '_res'] = max(0, reserved_count - qty)

    result = [(item[:-4], stock.get(item)) for item in stock.keys() if item.endswith('_res') and stock[item] > 0]
    return sorted(result)
