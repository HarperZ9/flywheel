def eval_bool(expr: str) -> bool:
    def parse_expr(index=0):
        if expr[index] == '(':
            index += 1
            truth = parse_truthy(index)
            index_ending = expr.find(')', index)
            return (expr[:index_ending+1], parse_expr(index_ending+1))
        else:
            return (expr[:index+1], index + 1)

    def parse_truthy(index=0):
        if expr[index] == 'T':
            return ('T', index + 1)
        elif expr[index] == 'F':
            return ('F', index + 1)
        else:
            op, index = expr[index:index+2]
            left_expr, index = parse_expr(index + 2)
            right_expr, index = parse_truthy(index)
            if op not in ['and', 'or', 'not']:
                raise ValueError('bad expr')
            return (op.join((left_expr, right_expr)), index)

    result, _ = parse_truthy()
    try:
        bool(result)  # Convert the truthy expression to a boolean
    except Exception as e:
        raise ValueError('bad expr') from e
    return eval(result)
