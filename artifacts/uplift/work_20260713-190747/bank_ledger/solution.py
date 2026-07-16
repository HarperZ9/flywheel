def bank_ledger(ops):
    if not all(isinstance(op, tuple) and len(op) == 2 for op in ops):
        raise ValueError('bad op')
    
    balance = 0
    result = []
    
    for op, amount in ops:
        if op not in ('deposit', 'withdraw'):
            raise ValueError('bad op')
        
        if not isinstance(amount, int) or amount < 1:
            raise ValueError('bad amount')
        
        if op == 'deposit':
            balance += amount
        else:  # withdraw
            if amount > balance:
                raise ValueError(f'insufficient funds: need {amount} have {balance}')
            balance -= amount
        
        result.append(balance)
    
    return result
