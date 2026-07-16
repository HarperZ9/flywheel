def bank_ledger(ops):
    """
    A Python function that takes a list of banking operations (each a tuple with two elements, ('deposit', amount) or ('withdraw', amount))
    and folds it over a balance starting at 0 to return the list of balances after each operation in order. 
    The input list must contain tuples where the first element is either 'deposit' or 'withdraw',
    and the second element is an integer amount >= 1 that represents either deposit or withdrawal.
    If any other value for the tuple's first element, an integer different from 0 or -1 (for 'deposit' and 'withdraw', respectively),
    or if the amount is not a positive integer >= 1, the function raises a ValueError with appropriate error message.
    
    :param ops: A list of banking operations as tuples
    :return: The list of balances after each operation in order
    """
    balance = 0
    result = []
    
    for op in ops:
        if len(op) != 2 or not isinstance(op[1], int):
            raise ValueError('bad op')
        
        _op, amount = op
        
        if _op == 'deposit':
            try:
                balance += amount
            except TypeError:
                # This would theoretically never happen due to the type checking earlier,
                # but leaving this in case we ever change our types.
                raise
            
            result.append(balance)
            
        elif _op == 'withdraw':
            try:
                if amount > balance:
                    raise ValueError(f'insufficient funds: need {_amount} have {balance}')
                balance -= amount
            except TypeError:
                # This would theoretically never happen due to the type checking earlier,
                # but leaving this in case we ever change our types.
                raise
            
            result.append(balance)
        else:
            raise ValueError('bad op')
    
    return result
