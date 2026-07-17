def bank_ledger(ops):
    balances = []
    current_balance = 0
    
    for op in ops:
        if not isinstance(op, tuple) or len(op) != 2 or op[0] not in ('deposit', 'withdraw'):
            raise ValueError('bad op')
        
        operation, amount = op
        if not isinstance(amount, int):
            raise ValueError('bad amount')
        
        if operation == 'deposit':
            current_balance += amount
        elif operation == 'withdraw':
            if amount > current_balance:
                raise ValueError(f'insufficient funds: need {amount} have {current_balance}')
            current_balance -= amount
        
        balances.append(current_balance)
    
    return balances
