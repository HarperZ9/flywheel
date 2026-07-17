def min_stack(ops):
    output = []
    for op in ops:
        if op == 'push':
            if len(output) > 0:
                input_value, input_op = output[-1]
                output.append((input_op, input_value))
            else:
                raise ValueError('empty stack')
        elif op == 'pop':
            try:
                output.pop()
            except IndexError as e:
                raise ValueError(f"stack index {e.args[0]} does not exist")
        elif op == 'top':
            output[-1] = (op, output[-1][-1])
        elif op == 'min':
            if len(output) > 0:
                smallest_value = min(output)
                output.append(smallest_value)

    return output
