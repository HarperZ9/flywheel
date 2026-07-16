def topo_sort(n, edges):
    from collections import defaultdict
    
    if n == 0:
        return []
    
    # Build the graph and in-degree dictionary
    graph = defaultdict(list)
    in_degree = {i: 0 for i in range(n)}
    
    for u, v in edges:
        graph[u].append(v)
        in_degree[v] += 1
    
    # Find all nodes with zero in-degree
    queue = [node for node in in_degree if in_degree[node] == 0]
    
    top_order = []
    
    while queue:
        node = queue.pop(0)
        top_order.append(node)
        
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
                
    # Check if there was a cycle (not all nodes are visited)
    if len(top_order) != n:
        return None
    
    return top_order
