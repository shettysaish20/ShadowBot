import networkx as nx

class DAG:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_node(self, node):
        """Adds a node to the DAG."""
        self.graph.add_node(node)

    def add_edge(self, u, v):
        """Adds an edge from node u to node v. Checks for cycles before adding the edge."""
        try:
            self.graph.add_edge(u, v)
            nx.find_cycle(self.graph)
            self.graph.remove_edge(u, v)
            raise nx.NetworkXUnfeasible("Adding this edge would create a cycle.")
        except nx.NetworkXNoCycle:
            pass  # No cycle, so the edge is valid
        except nx.NetworkXUnfeasible as e:
            print(f"Error: {e}")
            self.graph.remove_edge(u, v) # Ensure the invalid edge is removed
            return False
        return True

    def is_cyclic(self):
        """Checks if the DAG contains cycles."""
        try:
            nx.find_cycle(self.graph)
            return True
        except nx.NetworkXNoCycle:
            return False

    def topological_sort(self):
        """Performs topological sorting of the DAG."""
        if self.is_cyclic():
            print("Error: Cannot perform topological sort on a cyclic graph.")
            return None
        return list(nx.topological_sort(self.graph))

# Example Usage:
if __name__ == "__main__":
    dag = DAG()

    # Add nodes
    dag.add_node("A")
    dag.add_node("B")
    dag.add_node("C")
    dag.add_node("D")

    # Add edges
    dag.add_edge("A", "B")
    dag.add_edge("A", "C")
    dag.add_edge("B", "D")
    dag.add_edge("C", "D")

    # Attempt to add an edge that creates a cycle
    if dag.add_edge("D", "A"):
      print("Cycle added!")
    else:
      print("Could not add cycle.")

    # Check for cycles
    if dag.is_cyclic():
        print("The graph contains cycles.")
    else:
        print("The graph is acyclic.")

    # Perform topological sort
    topological_order = dag.topological_sort()
    if topological_order:
        print("Topological order:", topological_order)
