def stock_spans(prices):
    if not all(isinstance(price, (int, float)) for price in prices) or any(not isinstance(price, bool) for price in prices):
        raise ValueError('bad price')
    
    n = len(prices)
    spans = [0] * n  # Initialize spans list with zeros
    stack = []  # Stack to keep track of indices
    
    for i in range(n-1, -1, -1):  # Iterate from end to start
        price = prices[i]
        while stack and prices[stack[-1]] <= price:
            stack.pop()  # Remove elements from stack that are not greater than current price
        if stack:
            spans[i] = stack[-1] - i + 1  # Number of consecutive days with equal or lower prices
        else:
            spans[i] = i + 1  # If no earlier day had a higher price, span is index+1
        stack.append(i)  # Add current index to stack
    
    return spans
