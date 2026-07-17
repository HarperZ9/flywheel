def has_cycle(nxt):
    # Check if n is an empty list, return False
    if not nxt:
        return False

    for i in range(len(nxt)):
        val = nxt[i]
        if val == -1:  # Node has a link pointing to itself (cycle)
            break
        # Move to the node with the next link
        nxt = [val, nxt[nxt.index(val) + 1]]

    # Check each node's value to see if it matches its parent node index (-1 means not matching)
    for i in range(len(nxt)):
        if nxt[i] != -1:
            return False

    return True
