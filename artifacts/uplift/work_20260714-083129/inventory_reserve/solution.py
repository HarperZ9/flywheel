def reserve_trace(stock, ops):
    if not isinstance(stock, dict) or not all(isinstance(val, int) and val >= 0 for val in stock.values()):
        raise ValueError('bad stock')
    
    final_reservations = []

    for op in ops:
        if len(op) != 3 or op[0] not in ['reserve', 'cancel'] or not isinstance(op[2], int) or op[2] < 1 or op[1] not in stock:
            raise ValueError('bad op')
        
        item, qty = op[1], op[2]
        
        if op[0] == 'reserve':
            current_reservations = stock[item]
            
            if qty > (stock[item] - current_reservations):
                msg = f'not enough {item}'
                raise ValueError(msg)
            
            stock[item] += qty
            final_reservations.append((item, stock[item]))
        elif op[0] == 'cancel':
            if qty > current_reservations:
                msg = f'over-cancel of {item} reservations'
                raise ValueError(msg)
            
            stock[item] -= qty
            if stock[item] < 0:
                msg = f'unexpected negative reservation count for {item}'
                raise ValueError(msg)
            final_reservations.append((item, stock[item]))
    
    return sorted(final_reservations, key=lambda x: x[0])
