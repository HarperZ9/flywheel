def stock_spans(prices):
    if not all(isinstance(price, (int, float)) for price in prices) or any(not isinstance(price, bool) for price in prices):
        raise ValueError('bad price')
    
    spans = []
    if not prices:
        return spans
    
    stack = []  # To store indices
    for i, price in enumerate(prices):
        while stack and prices[stack[-1]] <= price:
            index = stack.pop()
            spans[index] = i - stack[-1] - 1  # Calculate span length from bottom of stack to current index
        if not stack or prices[stack[-1]] < price:
            stack.append(i)
    
    for index in range(len(prices) - 2, -1, -1):
        while stack and prices[stack[-1]] <= prices[index]:
            stack.pop()
        spans[index] = (index + 1 if not stack else stack[-1] - index)  # Calculate span length from current to top of stack
        stack.append(index)
    
    return spans
