import networkx as nx
import matplotlib.pyplot as plt

class DAG:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_node(self, node):
        self.graph.add_node(node)

    def add_edge(self, u, v):
        self.graph.add_edge(u, v)

    def is_cyclic_util(self, v, visited, stack):
        visited[v] = True
        stack[v] = True
        for neighbor in self.graph.neighbors(v):
            if not visited[neighbor]:
                if self.is_cyclic_util(neighbor, visited, stack):
                    return True
            elif stack[neighbor]:
                return True
        stack[v] = False
        return False

    def is_cyclic(self):
        num_nodes = len(self.graph.nodes)
        visited = [False] * num_nodes
        stack = [False] * num_nodes
        for node in self.graph.nodes:
            if not visited[node]:
                if self.is_cyclic_util(node, visited, stack):
                    return True
        return False

    def visualize(self, filename='dag.png'):
        pos = nx.spring_layout(self.graph)
        nx.draw(self.graph, pos, with_labels=True, node_color='skyblue', node_size=1500, arrowsize=20)
        plt.savefig(filename)
        plt.close()

if __name__ == '__main__':
    dag = DAG()
    dag.add_node(0)
    dag.add_node(1)
    dag.add_node(2)
    dag.add_node(3)

    dag.add_edge(0, 1)
    dag.add_edge(1, 2)
    dag.add_edge(2, 3)
    dag.add_edge(0, 2)

    if dag.is_cyclic():
        print("The DAG is cyclic.")
    else:
        print("The DAG is acyclic.")

    dag.visualize()