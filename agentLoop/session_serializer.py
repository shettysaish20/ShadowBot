"""
Centralized session serialization for NetworkX graphs
"""

import json
import networkx as nx
from pathlib import Path
from datetime import datetime
from typing import Optional

class SessionSerializer:
    """Centralized session serialization and loading"""
    
    @staticmethod
    def save_session(graph: nx.DiGraph, session_type: str = "regular", output_path: Optional[str] = None, original_session_file: Optional[Path] = None) -> Path:
        """
        Save NetworkX graph as session file
        
        Args:
            graph: NetworkX DiGraph to save
            session_type: "regular" for main sessions, "debug" for debug sessions
            output_path: Optional custom output path
            original_session_file: For debug sessions, reference to original file
            
        Returns:
            Path: The file path where session was saved
        """
        
        if output_path:
            # Use custom path
            session_file = Path(output_path)
        elif session_type == "debug":
            # Debug session path
            original_id = original_session_file.stem.replace('session_', '') if original_session_file else 'unknown'
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_file = Path(f"memory/debug_session_{original_id}_{timestamp}.json")
        else:
            # Regular session path with date structure
            base_dir = Path("memory/session_summaries_index")
            today = datetime.now()
            date_dir = base_dir / str(today.year) / f"{today.month:02d}" / f"{today.day:02d}"
            
            session_id = graph.graph['session_id']
            session_file = date_dir / f"session_{session_id}.json"
        
        # Create parent directories
        session_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Serialize graph
        graph_data = nx.node_link_data(graph, edges="links")
        
        # Write to file
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(graph_data, f, indent=2, default=str, ensure_ascii=False)
        
        return session_file
    
    @staticmethod
    def load_session(session_file: Path) -> nx.DiGraph:
        """
        Load NetworkX graph from session file
        
        Args:
            session_file: Path to session file
            
        Returns:
            nx.DiGraph: Loaded NetworkX graph
        """
        with open(session_file, 'r', encoding='utf-8') as f:
            graph_data = json.load(f)
        
        return nx.node_link_graph(graph_data, edges="links")
    
    @staticmethod
    def get_session_info(graph: nx.DiGraph) -> dict:
        """Get session metadata for display"""
        return {
            "session_id": graph.graph.get('session_id', 'unknown'),
            "created_at": graph.graph.get('created_at', 'unknown'),
            "original_query": graph.graph.get('original_query', 'No query'),
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges)
        } 