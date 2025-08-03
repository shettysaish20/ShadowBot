"""
NetworkX-based graph validation utilities
"""

import networkx as nx
from typing import List, Dict, Set, Optional, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

class GraphValidator:
    """Comprehensive graph validation using NetworkX features"""
    
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
    
    def validate_execution_graph(self, graph: nx.DiGraph, verbose: bool = True) -> Dict[str, any]:
        """
        Comprehensive validation of execution graph
        
        Returns:
            dict: Validation results with status and details
        """
        results = {
            "is_valid": True,
            "is_dag": False,
            "cycles": [],
            "disconnected_components": [],
            "orphaned_nodes": [],
            "root_nodes": [],
            "leaf_nodes": [],
            "warnings": [],
            "errors": []
        }
        
        # 1. Basic DAG validation
        try:
            results["is_dag"] = nx.is_directed_acyclic_graph(graph)
            if not results["is_dag"]:
                results["is_valid"] = False
                results["cycles"] = list(nx.simple_cycles(graph))
                results["errors"].append(f"Graph contains {len(results['cycles'])} cycles")
        except Exception as e:
            results["is_valid"] = False
            results["errors"].append(f"DAG validation failed: {e}")
        
        # 2. Connectivity analysis
        try:
            # Check for disconnected components
            if not nx.is_weakly_connected(graph):
                weak_components = list(nx.weakly_connected_components(graph))
                results["disconnected_components"] = [list(comp) for comp in weak_components]
                results["warnings"].append(f"Graph has {len(weak_components)} disconnected components")
            
            # Find root nodes (no predecessors, except ROOT)
            results["root_nodes"] = [n for n in graph.nodes() 
                                   if graph.in_degree(n) == 0 and n != "ROOT"]
            
            # Find leaf nodes (no successors)
            results["leaf_nodes"] = [n for n in graph.nodes() 
                                   if graph.out_degree(n) == 0]
            
            # Find orphaned nodes (no connections)
            results["orphaned_nodes"] = [n for n in graph.nodes() 
                                       if graph.degree(n) == 0 and n != "ROOT"]
            
        except Exception as e:
            results["warnings"].append(f"Connectivity analysis failed: {e}")
        
        # 3. Execution-specific validations
        try:
            self._validate_execution_requirements(graph, results)
        except Exception as e:
            results["warnings"].append(f"Execution validation failed: {e}")
        
        # 4. Display results if verbose
        if verbose:
            self._display_validation_results(results)
        
        return results
    
    def _validate_execution_requirements(self, graph: nx.DiGraph, results: Dict):
        """Validate execution-specific requirements"""
        
        # Check for ROOT node
        if "ROOT" not in graph.nodes():
            results["errors"].append("Missing ROOT node")
            results["is_valid"] = False
        
        # Check that all non-ROOT nodes have required attributes
        required_attrs = ["agent", "description", "status"]
        for node_id in graph.nodes():
            if node_id == "ROOT":
                continue
                
            node_data = graph.nodes[node_id]
            missing_attrs = [attr for attr in required_attrs if attr not in node_data]
            if missing_attrs:
                results["warnings"].append(f"Node {node_id} missing attributes: {missing_attrs}")
        
        # Check for dependency cycles in reads/writes
        try:
            dependency_issues = self._check_dependency_cycles(graph)
            if dependency_issues:
                results["warnings"].extend(dependency_issues)
        except Exception as e:
            results["warnings"].append(f"Dependency analysis failed: {e}")
    
    def _check_dependency_cycles(self, graph: nx.DiGraph) -> List[str]:
        """Check for logical dependency cycles in reads/writes"""
        issues = []
        
        # Build dependency graph based on reads/writes
        dep_graph = nx.DiGraph()
        
        for node_id in graph.nodes():
            if node_id == "ROOT":
                continue
                
            node_data = graph.nodes[node_id]
            writes = set(node_data.get("writes", []))
            reads = set(node_data.get("reads", []))
            
            # Add node to dependency graph
            dep_graph.add_node(node_id, writes=writes, reads=reads)
        
        # Add edges based on read/write dependencies
        for node_id in dep_graph.nodes():
            node_reads = dep_graph.nodes[node_id]["reads"]
            
            for other_node in dep_graph.nodes():
                if other_node == node_id:
                    continue
                    
                other_writes = dep_graph.nodes[other_node]["writes"]
                
                # If this node reads what another writes, create dependency
                if node_reads & other_writes:  # Set intersection
                    dep_graph.add_edge(other_node, node_id)
        
        # Check for cycles in dependency graph
        if not nx.is_directed_acyclic_graph(dep_graph):
            cycles = list(nx.simple_cycles(dep_graph))
            for cycle in cycles:
                issues.append(f"Dependency cycle detected: {' → '.join(cycle + [cycle[0]])}")
        
        return issues
    
    def _display_validation_results(self, results: Dict):
        """Display validation results using Rich"""
        
        # Overall status
        status_color = "green" if results["is_valid"] else "red"
        status_text = "✅ VALID" if results["is_valid"] else "❌ INVALID"
        
        self.console.print(Panel(
            f"🔍 Graph Validation Results\n\n"
            f"Status: [{status_color}]{status_text}[/{status_color}]\n"
            f"Is DAG: {'✅' if results['is_dag'] else '❌'}\n"
            f"Nodes: {len(results.get('root_nodes', []))} roots, {len(results.get('leaf_nodes', []))} leaves",
            title="📊 Validation Summary",
            border_style=status_color
        ))
        
        # Errors
        if results["errors"]:
            self.console.print("\n❌ **ERRORS:**")
            for error in results["errors"]:
                self.console.print(f"  • {error}")
        
        # Warnings  
        if results["warnings"]:
            self.console.print("\n⚠️  **WARNINGS:**")
            for warning in results["warnings"]:
                self.console.print(f"  • {warning}")
        
        # Cycles
        if results["cycles"]:
            self.console.print(f"\n🔄 **CYCLES DETECTED:**")
            for i, cycle in enumerate(results["cycles"], 1):
                cycle_str = " → ".join(cycle + [cycle[0]])
                self.console.print(f"  {i}. {cycle_str}")
        
        # Disconnected components
        if results["disconnected_components"]:
            self.console.print(f"\n🔗 **DISCONNECTED COMPONENTS:**")
            for i, component in enumerate(results["disconnected_components"], 1):
                self.console.print(f"  {i}. {component}")

    def analyze_critical_path(self, graph: nx.DiGraph) -> Dict[str, any]:
        """Analyze execution critical path using NetworkX algorithms"""
        
        if not nx.is_directed_acyclic_graph(graph):
            return {"error": "Cannot analyze critical path: graph contains cycles"}
        
        try:
            # Find longest path (critical path) using topological sort
            topo_order = list(nx.topological_sort(graph))
            
            # Calculate longest distances
            distances = {}
            for node in topo_order:
                if graph.in_degree(node) == 0:  # Root nodes
                    distances[node] = 0
                else:
                    distances[node] = max(
                        distances[pred] + 1 
                        for pred in graph.predecessors(node)
                    )
            
            # Find critical path
            max_distance = max(distances.values())
            critical_nodes = [node for node, dist in distances.items() if dist == max_distance]
            
            # Build actual critical path
            critical_path = []
            current = critical_nodes[0]  # Start with one of the furthest nodes
            
            while current:
                critical_path.insert(0, current)
                predecessors = [p for p in graph.predecessors(current) 
                              if distances[p] == distances[current] - 1]
                current = predecessors[0] if predecessors else None
            
            return {
                "critical_path": critical_path,
                "path_length": max_distance,
                "total_nodes": len(graph.nodes()),
                "parallel_opportunities": len(graph.nodes()) - max_distance - 1
            }
            
        except Exception as e:
            return {"error": f"Critical path analysis failed: {e}"}

    def find_blocked_nodes(self, graph: nx.DiGraph) -> Dict[str, List[str]]:
        """Find nodes that cannot execute due to failed dependencies"""
        blocked_nodes = {}
        
        for node_id in graph.nodes():
            if node_id == "ROOT":
                continue
                
            node_status = graph.nodes[node_id].get('status', 'pending')
            if node_status in ['completed', 'running']:
                continue
            
            # Check if any ancestor has failed
            ancestors = nx.ancestors(graph, node_id)
            failed_ancestors = [
                ancestor for ancestor in ancestors 
                if graph.nodes[ancestor].get('status') == 'failed'
            ]
            
            if failed_ancestors:
                blocked_nodes[node_id] = failed_ancestors
        
        return blocked_nodes