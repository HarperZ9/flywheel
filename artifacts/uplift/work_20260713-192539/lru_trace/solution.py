def lru_trace(capacity, ops):
    if not isinstance(capacity, int) or capacity < 1:
        raise ValueError('bad capacity')
    
    class LRUCacheNode:
        def __init__(self, key, value=None):
            self.key = key
            self.value = value
            self.prev = None
            self.next = None
    
    cache = {}
    dummy_head = LRUCacheNode('__dummy_head__')
    tail = LRUCacheNode('__dummy_tail__')
    dummy_head.next = tail
    tail.prev = dummy_head

    def get(key):
        if key not in cache:
            return None
        node = cache[key]
        move_to_end(node)
        return node.value

    def put(key, value=None):
        if key in cache:
            node = cache.pop(key)
            move_to_end(node)  # Move the existing key to the end (most recent use)
        else:
            if len(cache) == capacity:
                lru_node = dummy_head.next.prev
                del cache[lru_node.key]
                remove_and_delete_next(dummy_head, lru_node)

        new_node = LRUCacheNode(key, value)
        add_to_end(new_node)
    
    def move_to_end(node):
        prev_node = node.prev
        next_node = node.next
        if not prev_node or not next_node:
            return  # Node is already at the end

        remove_and_delete_next(prev_node, node)
        add_to_end(node)

    def add_to_end(node):
        tail.prev.next = node
        node.prev = tail.prev
        node.next = tail
        tail.prev = node
    
    def remove_and_delete_next(dummy_head, node):
        prev_node = dummy_head.next
        if node == dummy_head.next:
            return  # Node is already at the end

        prev_node.next = node.next
        node.next.prev = prev_node
        del cache[node.key]
    
    for _, op in ops:
        if op[0] == 'get':
            result = get(op[1])
        elif op[0] == 'put':
            put(*op)
        else:
            raise ValueError('bad op')

    return [result for result, _ in ops]
