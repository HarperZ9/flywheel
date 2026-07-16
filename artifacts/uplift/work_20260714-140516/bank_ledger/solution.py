def bank_ledger(ops):
    balances = []
    balance = 0
    for op in ops:
        if not isinstance(op, tuple) or len(op) != 2:
            raise ValueError('bad op')
        action, amount = op
        if action not in ('deposit', 'withdraw'):
            raise ValueError('bad op')
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise ValueError('bad amount')
        if amount < 1:
            raise ValueError('bad amount')
        if action == 'deposit':
            balance += amount
        else:  # withdraw
            if amount > balance:
                raise ValueError(f'insufficient funds: need {amount} have {balance}')
            balance -= amount
        balances.append(balance)
    return balances
