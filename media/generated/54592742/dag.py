### Design Details: ###
# This script demonstrates the creation and manipulation of a Directed Acyclic Graph (DAG) using the graphlib module.
# It includes functionalities for adding nodes, edges, and performing a topological sort. The code is well-commented
# and includes exception handling for robustness.

import graphlib

class DAG:
    def __init__(self):
        # Initialize the DAG with an empty dictionary to store dependencies.
        # The keys are nodes, and the values are sets of their dependencies.
        self.graph = {}

    def add_node(self, node):
        # Add a node to the DAG. If the node already exists, this is a no-op.
        if node not in self.graph:
            self.graph[node] = set()

    def add_edge(self, from_node, to_node):
        # Add a directed edge from from_node to to_node, indicating that to_node depends on from_node.
        # If either node doesn't exist, it will be added to the graph.
        if from_node not in self.graph:
            self.add_node(from_node)
        if to_node not in self.graph:
            self.add_node(to_node)
        self.graph[to_node].add(from_node)

    def topological_sort(self):
        # Perform a topological sort of the DAG.
        # This returns a linear ordering of nodes such that for every directed edge from node A to node B,
        # node A appears before node B in the ordering.
        # Uses graphlib.TopologicalSorter for the sorting logic.
        try:
            ts = graphlib.TopologicalSorter(self.graph)
            return list(ts.static_order())
        except graphlib.CycleError as e:
            # Handle the case where a cycle is detected in the graph, which prevents topological sorting.
            raise ValueError("Cycle detected in the DAG: Topological sort not possible.") from e


# Example Usage:
if __name__ == "__main__":
    # Create an instance of the DAG.
    dag = DAG()

    # Add nodes to the DAG.
    dag.add_node("A")
    dag.add_node("B")
    dag.add_node("C")
    dag.add_node("D")
    dag.add_node("E")

    # Add edges to define dependencies between the nodes.
    dag.add_edge("A", "B")  # B depends on A
    dag.add_edge("A", "C")  # C depends on A
    dag.add_edge("B", "D")  # D depends on B
    dag.add_edge("C", "E")  # E depends on C

    # Attempt to perform a topological sort and print the sorted order.
    try:
        sorted_nodes = dag.topological_sort()
        print("Topological Sort Order:", sorted_nodes)
    except ValueError as e:
        # Handle any ValueErrors that occur during topological sorting, such as cycle detection.
        print(f"Error: {e}")
