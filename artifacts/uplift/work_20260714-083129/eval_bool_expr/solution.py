def eval_bool(expr):
    def parse_expr(index=0):
        if index == len(expr) or expr[index] == 't':
            return True, index + 1
        elif expr[index] == 'f':
            return False, index + 1
        else:
            raise ValueError('bad expr')

    def evaluate(group_start_index, group_end_index):
        sub_expr = expr[group_start_index:group_end_index]
        if not any(sub in sub_expr for sub in ['and', 'or', 'not']):
            return parse_expr(index=group_start_index)
        
        operator_position = max([(sub_expr.index(op), op) for op in ['and', 'or']][0] if len([op for op in ['and', 'or'] if op in sub_expr]) > 1 else -1, key=lambda k: (k, sub_expr[k-1:k].strip() and sub_expr[k+1:k+2]) is not None)
        
        left = evaluate(group_start_index, operator_position) if operator_position != -1 else parse_expr(index=group_start_index)

        op = 'and' if sub_expr[operator_position] == '&' else ('or' if sub_expr[operator_position] == '|' else 'not')
        right = evaluate(operator_position + 1, group_end_index - 1)
        
        return (left if op != 'not' or not left else not left), group_end_index

    try:
        return evaluate(0, len(expr))
    except Exception as e:
        raise ValueError('bad expr') from e
