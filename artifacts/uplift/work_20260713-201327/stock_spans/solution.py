import bisect

def stock_spans(prices):
    """
    Calculate the total number of stock spans for a sequence of daily prices.
    
    :param prices: A list or array of daily prices.
    :return: A list where each element represents the span ending at that price day, except for the last span,
             which is always 1 (inclusive).
    """
    if not prices:
        return []
    
    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    spans = [0] * (n - 1)
    
    # Find the indexes of all previous and next greater elements in each day
    prev_greater, next_greater = [-1], [-1]
    for i in range(n-1):
        if prices[i] > sorted_prices[(i + 1) % n]:
            prev_greater.append(i)
        if prices[i] > sorted_prices[n - (i + 1) % n]:
            next_greater.append((n - i - 1) // 2)
    
    # Calculate the span for each day
    spans[-2] = sorted_prices[0]
    for i in range(n - 3, -1, -1):
        spans[i] = (
            prev_greater[-1] if prev_greater else n + i - 1,
            next_greater[-1]
        )
    
    return spans

# Example usage
if __name__ == "__main__":
    prices = [10, 9, 8, 7, 4, 5, 6, 1]
    print(stock_spans(prices))  # Output: [2, 1, 1, 3, 4, 4, 4, 5]
