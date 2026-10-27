class Node:
    __slots__ = ("next",)

    def __init__(self):
        self.next = None


node_count = 8192
nodes = [Node() for _ in range(node_count)]
for index, node in enumerate(nodes):
    node.next = nodes[(index + 257) & (node_count - 1)]

current = nodes[0]
for _ in range(4_000_000):
    current = current.next

print(nodes.index(current))
