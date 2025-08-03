import asyncio
import networkx as nx
from datetime import datetime
from rich.console import Console
from rich.text import Text
from rich.live import Live
from rich.tree import Tree
from rich.layout import Layout
from rich.panel import Panel
from rich.align import Align
from rich.table import Table

class ExecutionVisualizer:
    def __init__(self, context):
        """Reference the same NetworkX graph instead of rebuilding"""
        self.context = context
        self.G = context.plan_graph  # Direct reference to same graph
        self.log_messages = []  # Initialize log messages list

    def get_log_panel(self):
        log_text = "\n".join(self.log_messages) or "🚀 Starting execution..."
        return Panel(Align.left(log_text), title="📋 Execution Log", border_style="cyan")

    def build_tree(self, node_id="ROOT", visited_global=None):
        """Build tree showing actual DAG structure with proper convergence handling"""
        if visited_global is None:
            visited_global = set()
        
        def build_subtree(current_node, path_visited):
            # Prevent infinite loops in current path
            if current_node in path_visited:
                return Tree(Text(f"[CYCLE: {current_node}]", style="red"))
            
            path_visited = path_visited | {current_node}
            
            node_data = self.G.nodes[current_node]
            status = node_data["status"]
            agent = node_data["agent"]
            description = node_data["description"]
            
            # Status symbols
            status_symbol = {
                "pending": "🔲", "running": "🔄", "completed": "✅", "failed": "❌"
            }[status]
            
            # Format label
            if current_node == "ROOT":
                label = Text(f"ROOT {status_symbol} {description}")
            else:
                short_desc = description[:60] + "..." if len(description) > 60 else description
                label = Text(f"{current_node} {status_symbol} {agent} → {short_desc}")
            
            # Styling
            if status == "completed":
                label.stylize("green")
            elif status == "running":
                label.stylize("yellow") 
            elif status == "failed":
                label.stylize("red")
            else:
                label.stylize("dim")
            
            tree = Tree(label)
            
            # Get successors
            successors = list(self.G.successors(current_node))
            
            if not successors:
                return tree
            
            # Check each successor for convergence
            for child in successors:
                parents = list(self.G.predecessors(child))
                
                if len(parents) > 1:
                    # This is a convergence node
                    if child not in visited_global:
                        # First time seeing this convergence node - show it with all parents
                        visited_global.add(child)
                        
                        # Create convergence indicator
                        parent_names = [p for p in parents if p != current_node]
                        if parent_names:
                            conv_label = Text(f"[+ {', '.join(parent_names)}] → {child}")
                            conv_label.stylize("cyan bold")
                            conv_tree = Tree(conv_label)
                            conv_tree.add(build_subtree(child, path_visited))
                            tree.add(conv_tree)
                        else:
                            # This is the last parent to reach convergence
                            tree.add(build_subtree(child, path_visited))
                    else:
                        # Already shown this convergence node
                        ref_label = Text(f"→ {child} [see above]")
                        ref_label.stylize("dim italic")
                        tree.add(Tree(ref_label))
                else:
                    # Regular single-parent node
                    tree.add(build_subtree(child, path_visited))
            
            return tree
        
        return build_subtree(node_id, set())

    def get_layout(self):
        """Layout exactly like your test.py"""
        layout = Layout()
        layout.split_column(
            Layout(name="tree", ratio=3),
            Layout(name="log", size=8)
        )
        layout["tree"].update(
            Panel(self.build_tree(), title="🤖 Agent Execution DAG", border_style="white")
        )
        layout["log"].update(self.get_log_panel())
        return layout

    def add_log_message(self, message):
        """Add a log message for display"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_messages.append(f"[{timestamp}] {message}")
    
    def is_finished(self):
        """Check if execution is finished"""
        return all(
            self.G.nodes[n]["status"] in ["completed", "failed"] 
            for n in self.G.nodes if n != "ROOT"
        )
