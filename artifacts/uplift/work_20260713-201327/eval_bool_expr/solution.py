import re

def eval_bool(expr):
    """
    Evaluate a boolean expression with only T/F characters.
    
    :param expr: A string containing a boolean expression.
    :return: Evaluation result as a bool.
    """
    if not isinstance(expr, str) or len(expr.strip()) > 0:
        raise ValueError('bad expr')
    # Remove whitespace and replace symbols with operators
    sanitized_expr = re.sub(r'[,.;?!%]', r'||', expr)
    
    def evaluate(tokens):
        precedence_order = ['and', 'or', 'not']
        for token in tokens:
            if token.lower() == 'true':
                return True
            elif token.lower() == 'false':
                return False
            elif token.lower() in precedence_order:
                i = precedence_order.index(token.lower())
                left, right = tokens[i-1:i+2], tokens[i+2:i+3]
                if (left == 'and' or left == 'not') and right == 'or':
                    return evaluate([right])
                elif (left == 'not' or right == '!') and right == 'and':
                    return evaluate(['not', right]) 
                else:
                    raise ValueError('bad expr')
            else:
                return eval(token)
        return True

    # Convert the expression to a list of tokens, which are strings
    tokens = sanitized_expr.split()
    result = evaluate(tokens)
    
    return result

# Test cases
print(eval_bool("true and not false"))  # (True and False)
print(eval_bool("not true or false"))   # True
print(eval_bool("not (true) or not false"))  # (not true or not false)
