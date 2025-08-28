# DAG Theory:
# A Directed Acyclic Graph (DAG) is a graph with directed edges and no cycles.
# In simpler terms, it's a set of nodes connected by edges, where each edge has a direction,
# and it's impossible to start at one node and follow a path that leads back to the same node.
# DAGs are used to model dependencies, workflows, and processes where the order of operations matters.
# Examples: Task scheduling, data processing pipelines, dependency resolution in software.

class DAGNode:
    def __init__(self, name, operation=None):
        self.name = name
        self.operation = operation  # Function or task to be executed
        self.dependencies = []  # List of parent nodes (nodes that must be executed before this one)
        self.results = None

    def add_dependency(self, node):
        self.dependencies.append(node)

    def execute(self):
        # Ensure all dependencies are executed before executing this node
        for dependency in self.dependencies:
            if dependency.results is None:
                dependency.execute()

        # Execute the operation if it exists
        if self.operation:
            print(f"Executing {self.name}...")
            # UPDATE THIS: Handle operation execution and error handling
            self.results = self.operation()
            print(f"{self.name} completed.")
        else:
            print(f"Node {self.name} has no operation.")
            self.results = None  # Or some default value

        return self.results

def example_operation_1():
    # Example operation: simple addition
    print("Running example_operation_1...")
    # UPDATE THIS: Add more complex functionality here
    return 10 + 5

def example_operation_2():
    # Example operation: string concatenation
    print("Running example_operation_2...")
    # UPDATE THIS: Add more complex functionality here
    return "hello " + "world"

# Example DAG creation:
node_a = DAGNode("A", example_operation_1)
node_b = DAGNode("B", example_operation_2)
node_c = DAGNode("C")  # Node C depends on A and B, but has no operation itself

node_c.add_dependency(node_a)
node_c.add_dependency(node_b)

# Execute the DAG by executing the final node
print("Executing the DAG...")
result = node_c.execute()

print("DAG Execution Complete.")
print(f"Result of node C: {result}") # This would be None because node_c has no operation.

# UPDATE THIS: Add more nodes, operations, and dependencies to create a more complex DAG

# UPDATE THIS: Implement a DAG scheduler that can execute nodes in parallel when dependencies allow

# UPDATE THIS: Implement error handling and retry mechanisms
