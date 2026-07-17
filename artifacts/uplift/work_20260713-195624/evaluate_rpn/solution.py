def evaluate_rpn(tokens):
    import ast

    # Convert tokens to a valid Python expression tree
    tree = parse_expression(tokens)

    # Evaluate the expression based on the defined operators and sub-expressions
    result = eval_expression(tree)

    return str(result)
