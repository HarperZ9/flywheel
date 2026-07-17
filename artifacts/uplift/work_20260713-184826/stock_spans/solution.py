def stock_spans(prices):
    if not all(isinstance(x, (int, float)) for x in prices):
        raise ValueError('bad price')
    
    n = len(prices)
    spans = [1] * n  # Each day's span is at least 1
    
    for i in range(1, n):
        j = i
        while j > 0 and prices[j-1] <= prices[i]:
            j -= spans[j-1]
        spans[i] += (i - j)
    
    return spans
