def reserve_trace(stock, ops):
    if not isinstance(stock, dict) or len([x for x in stock.values() if not isinstance(x, int)]) > 0:
        raise ValueError('bad stock')

    final_reservations = []
    
    for op in ops:
        if len(op) != 3:
            raise ValueError('bad op')
        
        action, item, qty = op
        if not isinstance(qty, int):
            raise ValueError('bad qty')
        if item not in stock:
            raise ValueError('unknown item')

        available_stock = stock[item] - final_reservations[-1][1] if final_reservations else stock[item]
        if action == 'reserve':
            if qty > available_stock:
                raise ValueError(f'not enough {item}')
            remaining_qty = qty
            for _ in range(qty):
                reserved_item = (item, min(available_stock, 1))
                final_reservations.append(reserved_item)
                stock[item] -= 1
                available_stock -= 1
                if available_stock == 0:
                    break
    
    final_reservations.sort(key=lambda x: x[0])
    
    return final_reservations
