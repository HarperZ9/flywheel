def stock_spans(prices):
    if not isinstance(prices, (list, tuple)):
        raise ValueError('prices must be a list or tuple')
    spans = []
    for i, x in enumerate(prices):
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise ValueError('bad price')
        j = i - 1
        while j >= 0 and prices[j] <= x:
            j -= 1
        spans.append(i - j)
    return spans
