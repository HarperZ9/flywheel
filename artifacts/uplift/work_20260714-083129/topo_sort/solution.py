def topo_sort(n, edges):
    from collections import defaultdict, deque

    # Create an adjacency list representation of the graph
    graph = defaultdict(list)
    for u, v in edges:
        graph[u].append(v)

    # Initialize indegree array
    indegree = [0] * n
    for node in range(n):
        for neighbor in graph[node]:
            indegree[neighbor] += 1

    # Create a queue for nodes with zero indegree
    queue = deque([node for node in range(n) if not indegree[node]])

    # Initialize the result list and cycle flag
    topological_order = []
    has_cycle = False

    while queue:
        current_node = queue.popleft()
        topological_order.append(current_node)

        for neighbor in graph[current_node]:
            indegree[neighbor] -= 1
            if not indegree[neighbor]:
                queue.append(neighbor)
        
        # If a node's indegree becomes negative, we have a cycle
        if -indegree[neighbor] == 1:
            has_cycle = True

    if has_cycle:
        return None
    else:
        return topological_order
