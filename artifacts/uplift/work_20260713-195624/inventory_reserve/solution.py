def reserve_trace(stock, ops):
    def validate_and_reserve(item, qty, stock):
        if not isinstance(item, str) or not isinstance(qty, (int, bool)):
            raise ValueError('bad stock')
        available_stock = int(stock[item])
        try:
            res_item = 'reserve' + item
            new_reserved_count = max(0, available_stock - qty)
        except KeyError:
            raise ValueError(f'the {item} key is unknown in the stock dict')
        if not isinstance(new_reserved_count, (int, bool)):
            raise ValueError('bad qty')
        try:
            stock[new_reserved_item] = new_reserved_count
        except TypeError as e:
            raise ValueError(str(e))

    def validate_and_cancel(item, qty):
        for op in ops:
            try:
                if op[0] == 'cancel':
                    validate_and_reserve(item, -qty, stock)
                else:
                    raise ValueError(f'wrong operation: {op}')
            except (ValueError, TypeError) as e:
                raise ValueError(str(e))

    results = []
    for operation in ops:
        item, qty = operation
        try:
            validate_and_reserve(item, int(qty), stock)
            if int(qty) > 0 and int(qty) <= int(stock[item]):
                results.append((item, int(qty)))
            else:
                raise ValueError(f'not enough {item}')
        except (ValueError, TypeError):
            raise ValueError('bad op')
    return sorted(results)
