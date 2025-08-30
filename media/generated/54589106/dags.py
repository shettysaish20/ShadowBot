class DAGNode:
    def __init__(self, name):
        """Initialize a DAG node with a given name."""
        self.name = name
        self.parents = []  # List of parent nodes
        self.children = [] # List of child nodes

class DAG:
    def __init__(self):
        """Initialize an empty DAG."""
        self.nodes = {}

    def add_node(self, node_name):
        """Add a new node to the DAG."""
        if node_name not in self.nodes:
            self.nodes[node_name] = DAGNode(node_name)
        else:
            print(f"Node {node_name} already exists.")

    def add_edge(self, parent_name, child_name):
        """Add a directed edge from parent to child."""
        if parent_name not in self.nodes or child_name not in self.nodes:
            print("One or both nodes do not exist.  Please add the nodes first before adding the edge.")
            return

        parent_node = self.nodes[parent_name]
        child_node = self.nodes[child_name]

        if child_node not in parent_node.children:
            parent_node.children.append(child_node)
        if parent_node not in child_node.parents:
            child_node.parents.append(parent_node)

    def has_cycle_util(self, node_name, visited, stack):
        """Utility function to check for cycles using DFS."""
        visited[node_name] = True
        stack[node_name] = True

        for child_node in self.nodes[node_name].children:
            child_name = child_node.name
            if not visited[child_name]:
                if self.has_cycle_util(child_name, visited, stack):
                    return True
            elif stack[child_name]:
                return True

        stack[node_name] = False
        return False

    def has_cycle(self):
        """Check if the DAG contains any cycles."""
        visited = {node_name: False for node_name in self.nodes}
        stack = {node_name: False for node_name in self.nodes}

        for node_name in self.nodes:
            if not visited[node_name]:
                if self.has_cycle_util(node_name, visited, stack):
                    return True
        return False

    def topological_sort_util(self, node_name, visited, stack):
        """Utility function for topological sorting using DFS."""
        visited[node_name] = True

        for child_node in self.nodes[node_name].children:
            child_name = child_node.name
            if not visited[child_name]:
                self.topological_sort_util(child_name, visited, stack)

        stack.insert(0, node_name)

    def topological_sort(self):
        """Perform topological sorting on the DAG."""
        visited = {node_name: False for node_name in self.nodes}
        stack = []

        for node_name in self.nodes:
            if not visited[node_name]:
                self.topological_sort_util(node_name, visited, stack)

        return stack

# Example Usage:
dag = DAG()

# Add nodes
# Placeholder: Add your nodes here
nodes_to_add = ['A', 'B', 'C', 'D', 'E']
for node in nodes_to_add:
    dag.add_node(node)

# Add edges
# Placeholder: Define your edges here
edges_to_add = [('A', 'B'), ('A', 'C'), ('B', 'D'), ('C', 'E')]
for parent, child in edges_to_add:
    dag.add_edge(parent, child)

# Check for cycles
if dag.has_cycle():
    print("The DAG contains a cycle.")
else:
    print("The DAG does not contain any cycles.")

# Perform topological sort
topological_order = dag.topological_sort()
print("Topological order:", topological_order)
