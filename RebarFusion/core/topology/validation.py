from typing import List
import uuid

class GraphValidator:
    """
    Validates a TopologyGraph immediately after construction.
    Checks for zero-length edges, self-loops, duplicates, orphans.
    Returns a list of warnings.
    """
    def validate(self, graph, canonical_nodes) -> List[str]:
        warnings = []
        
        # 1. Zero-length edges
        zero_length = [e for e in graph.edges if e.length < 1e-5]
        if zero_length:
            warnings.append(f"Found {len(zero_length)} zero-length edges.")
            
        # 2. Self loops
        self_loops = [e for e in graph.edges if e.start_node == e.end_node]
        if self_loops:
            warnings.append(f"Found {len(self_loops)} self loops.")
            
        # 3. Duplicate edges
        seen = set()
        duplicates = 0
        for e in graph.edges:
            # Undirected edge representation
            rep = tuple(sorted([e.start_node, e.end_node]))
            if rep in seen:
                # We can't strictly call it a duplicate if they are different geometries
                # e.g. two parallel lines. But topological duplicates might be suspicious.
                # Just counting them for now.
                duplicates += 1
            else:
                seen.add(rep)
        
        if duplicates > 0:
            warnings.append(f"Found {duplicates} topologically duplicate edges (multiple edges between same nodes).")
            
        # 4. Orphan nodes (nodes with 0 degree)
        # Note: some canonical nodes might not end up in graph edges if they were text inserts
        # But if they were from lines/arcs they should have degree > 0
        orphan_count = 0
        for node in canonical_nodes:
            if graph.node_degrees.get(node.id, 0) == 0:
                # Let's see if this node has any line/arc/polyline references
                has_geom = any(ref[1] in ('start', 'end') or 'vertex' in ref[1] for ref in node.references)
                if has_geom:
                    orphan_count += 1
                    
        if orphan_count > 0:
            warnings.append(f"Found {orphan_count} orphan geometry nodes with degree 0.")
            
        return warnings
