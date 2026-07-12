import math
import heapq
import sqlite3
from database.db_helper import get_db_connection

class NavigationEngine:
    @staticmethod
    def get_graph():
        """
        Loads the graph structure from the database.
        Returns:
            nodes: dict of node_id -> {id, name, x, y}
            adjacency: dict of node_id -> list of (neighbor_id, distance)
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Load all nodes
        cursor.execute("SELECT id, node_name, x_coordinate, y_coordinate FROM navigation_nodes")
        nodes = {}
        for row in cursor.fetchall():
            nodes[row['id']] = {
                'id': row['id'],
                'name': row['node_name'],
                'x': row['x_coordinate'],
                'y': row['y_coordinate']
            }
            
        # Load all edges
        cursor.execute("SELECT source_node, destination_node, distance FROM navigation_edges")
        adjacency = {node_id: [] for node_id in nodes}
        for row in cursor.fetchall():
            src = row['source_node']
            dest = row['destination_node']
            dist = row['distance']
            # Safety check if nodes exist
            if src in adjacency and dest in adjacency:
                adjacency[src].append((dest, dist))
                
        conn.close()
        return nodes, adjacency

    @staticmethod
    def heuristic(node1, node2):
        """Euclidean distance heuristic for A*."""
        return math.sqrt((node1['x'] - node2['x'])**2 + (node1['y'] - node2['y'])**2)

    @classmethod
    def a_star(cls, source_id, target_id):
        """
        Calculates the shortest path using the A* algorithm.
        Returns:
            path: list of node dictionaries representing the path.
            total_distance: total path distance (float).
        """
        nodes, adjacency = cls.get_graph()
        
        if source_id not in nodes or target_id not in nodes:
            return None, 0.0

        # Min-priority queue: elements are (f_score, current_node_id)
        open_set = []
        heapq.heappush(open_set, (0.0, source_id))
        
        # Maps to track back-references and path costs
        came_from = {}
        g_score = {node_id: float('inf') for node_id in nodes}
        g_score[source_id] = 0.0
        
        f_score = {node_id: float('inf') for node_id in nodes}
        f_score[source_id] = cls.heuristic(nodes[source_id], nodes[target_id])
        
        in_open_set = {source_id}

        while open_set:
            _, current = heapq.heappop(open_set)
            in_open_set.remove(current)

            if current == target_id:
                # Reconstruct path
                path = []
                temp = current
                while temp in came_from:
                    path.append(nodes[temp])
                    temp = came_from[temp]
                path.append(nodes[source_id])
                path.reverse()
                return path, g_score[target_id]

            for neighbor, weight in adjacency[current]:
                tentative_g = g_score[current] + weight
                if tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + cls.heuristic(nodes[neighbor], nodes[target_id])
                    
                    if neighbor not in in_open_set:
                        heapq.heappush(open_set, (f_score[neighbor], neighbor))
                        in_open_set.add(neighbor)
                        
        return None, 0.0

    @classmethod
    def generate_directions(cls, path):
        """
        Generates screen-reader-friendly turn-by-turn spoken instructions.
        Args:
            path: list of node dicts from A* reconstruction.
        Returns:
            instructions: list of strings.
        """
        if not path or len(path) < 2:
            return ["You have arrived at your destination."]
            
        instructions = []
        
        # First step direction
        first_segment_dist = cls.heuristic(path[0], path[1])
        instructions.append(f"Start from {path[0]['name']}. Move straight towards {path[1]['name']} for {first_segment_dist:.1f} meters.")
        
        for i in range(1, len(path) - 1):
            n_prev = path[i-1]
            n_curr = path[i]
            n_next = path[i+1]
            
            # Vectors of current and next moves
            v1_x = n_curr['x'] - n_prev['x']
            v1_y = n_curr['y'] - n_prev['y']
            v2_x = n_next['x'] - n_curr['x']
            v2_y = n_next['y'] - n_curr['y']
            
            # Angles relative to Y-axis
            a1 = math.atan2(v1_x, v1_y)
            a2 = math.atan2(v2_x, v2_y)
            
            turn = a2 - a1
            # Normalize to [-pi, pi]
            while turn > math.pi: turn -= 2 * math.pi
            while turn < -math.pi: turn += 2 * math.pi
            
            turn_deg = math.degrees(turn)
            dist = cls.heuristic(n_curr, n_next)
            
            # Direct translation of turns
            if abs(turn_deg) < 30:
                action = "Continue straight"
            elif 30 <= turn_deg < 120:
                action = "Turn right"
            elif -120 < turn_deg <= -30:
                action = "Turn left"
            else:
                action = "Turn around"
                
            instructions.append(f"At {n_curr['name']}, {action} and walk {dist:.1f} meters to {n_next['name']}.")
            
        instructions.append("You have reached your destination.")
        return instructions

    @classmethod
    def get_room_node_id(cls, search_query):
        """
        Resolves room number, building name, or nodes to their node ID.
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Clean query
        q = search_query.strip().lower()
        
        # 1. Check exact node name
        cursor.execute("SELECT id FROM navigation_nodes WHERE LOWER(node_name) = ?", (q,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return row['id']
            
        # 2. Check room number
        cursor.execute("SELECT node_id FROM rooms WHERE LOWER(room_number) = ? AND node_id IS NOT NULL", (q,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return row['node_id']
            
        # 3. Fuzzy match Room numbers in node names
        cursor.execute("SELECT id FROM navigation_nodes WHERE LOWER(node_name) LIKE ?", (f"%{q}%",))
        row = cursor.fetchone()
        if row:
            conn.close()
            return row['id']
            
        conn.close()
        return None
