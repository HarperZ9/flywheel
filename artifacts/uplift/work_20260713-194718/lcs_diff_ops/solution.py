def diff_ops(a, b):
    def lcs(x, y):
        x_len = len(x)
        y_len = len(y)
        
        # Create an array to hold lengths of Longest Common Subsequences for all subproblems
        dp = [[0] * (y_len + 1) for _ in range(x_len + 1)]
        
        # Fill the DP table from bottom-up fashion
        for i in range(1, x_len + 1):
            for j in range(1, y_len + 1):
                if x[i - 1] == y[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        
        return dp

    def backtrack(x, y, dp):
        i, j = len(x) - 1, len(y) - 1
        while i >= 0 and j >= 0:
            if x[i] == y[j]:
                yield (i, j)
                i -= 1
                j -= 1
            elif dp[i + 1][j] > dp[i][j + 1]:
                i -= 1
            else:
                j -= 1

    def find_ops(x, y):
        x_len = len(x)
        y_len = len(y)
        
        if not (x and y): 
            return []
        
        dp = lcs(x, y)
        result = list(backtrack(x, y, dp))
        
        ops = ['delete'] * (len(x) - result[-1][0]) + ['insert'] * (result[0][0] - len(y) + 1)
        for i in range(len(result) - 2, -1, -1):
            if result[i + 1][0] > result[i][0]:
                ops[result[i][0]:result[i + 1][0]] = ['delete'] * (result[i + 1][0] - result[i][0])
            elif result[i + 1][0] < result[i][0]:
                ops[result[i][0]:result[i + 1][0]] = ['insert'] * (result[i][0] - result[i + 1][0])
        if len(ops) > 0 and ops[-1] != ops[0]:
            ops.insert(0, ops.pop())
        
        return ops

    def diff_elements(a, b):
        a_len = len(a)
        b_len = len(b)

        # Find LCS
        dp_lcs = lcs(a, b)
        start_a, end_a = dp_lcs[-1][-1], dp_lcs[0][0]
        
        if not (a and b): 
            return []
        
        # Find indices where elements can be deleted from a to minimize diff length
        ops = find_ops(a[start_a:end_a+1], b[start_a:end_a+1])
        
        # Initialize variables for building the final result
        inserted_items, op_count, start_insertion_point, tag = [], 0, None, ''
        
        for i in range(len(ops)):
            if ops[i] == 'insert':
                inserted_items.append(a[end_a + tag])  
                tag = a[end_a + tag]
            elif ops[i] == 'delete' and len(inserted_items) != 0:
                op_count += 1
                start_insertion_point = end_a + tag
                tag = None
        return [(tag, inserted_items
