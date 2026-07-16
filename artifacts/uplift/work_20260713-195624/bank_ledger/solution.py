def bank_ledger(ops):
    """
    Fold a list of banking operations over a balance that starts at 0.
    
    Each element of ops must be one of two forms:
    "deposit" or "withdraw".
    
    >>> bank_ledger([("deposit", 5), ("withdraw", -10)])
    [5, 5]
    """
    current_balance = 0
    for op in ops:
        action, amount = op
        if action == 'deposit':
            current_balance += amount
            # Check balance
            if not isinstance(current_balance, (int, float)) or len(str(current_balance)) > 1:
                raise ValueError('bad op')
            if amount < 0:
                raise ValueError('insufficient funds: need N have B', -abs(amount), str(current_balance))
        elif action == 'withdraw':
            # Check withdrawal
            if not isinstance(amount, (int, float)) or len(str(amount)) > 1:
                raise ValueError('bad op')
            current_balance -= amount
    return [current_balance]
def check_function():
    ops = [("deposit", 5), ("withdraw", -10)]
    result = bank_ledger(ops)
    assert result == [5, 5], f"Expected {result}, got {result}"

    ops = []
    result = bank_ledger(ops)
    assert result == [], f"Expected {result}, got []"

if __name__ == "__main__":
    check_function()
