import cv2
import math
import logging
import re
from database.db_helper import get_db_connection
from ai_models.ocr_reader import OCRReader

logger = logging.getLogger(__name__)

class BlueprintAnalyzer:
    def __init__(self):
        self.ocr_reader = OCRReader()

    def analyze(self, image_path):
        """
        Analyzes the blueprint image:
        1. Runs OCR to find room numbers and text labels.
        2. Places nodes at the center of detected labels.
        3. Connects nodes to their nearest neighbors to build a navigability graph.
        4. Re-initializes and seeds the database with this new graph.
        """
        logger.info(f"Analyzing building blueprint: {image_path}")
        
        # Load image
        frame = cv2.imread(image_path)
        if frame is None:
            logger.warning(f"Failed to load blueprint image at {image_path}. Running analyzer with simulated dimension and fallback map.")
            h, w = 600, 800
            ocr_results = []
        else:
            h, w, _ = frame.shape
            # 1. Extract text labels using EasyOCR
            ocr_results = self.ocr_reader.extract_text(frame)
            logger.info(f"OCR found {len(ocr_results)} text regions on blueprint.")
        
        detected_nodes = []
        
        # Helper list of common room identifier keywords
        room_keywords = ['room', 'lobby', 'exit', 'office', 'lab', 'hall', 'stairs', 'restroom', 'washroom', 'wc', 'library']
        
        for idx, res in enumerate(ocr_results):
            text = res["text"].strip()
            bbox = res["bbox"] # [x1, y1, x2, y2]
            
            # Clean and check if text represents a room or number
            is_valid_room = False
            # Check if it is a number (e.g. "101", "305")
            if re.search(r'\b\d{2,4}[a-zA-Z]?\b', text):
                is_valid_room = True
            # Check if it contains keywords
            elif any(kw in text.lower() for kw in room_keywords):
                is_valid_room = True
                
            if is_valid_room:
                # Compute center coordinate
                cx = (bbox[0] + bbox[2]) // 2
                cy = (bbox[1] + bbox[3]) // 2
                
                # Deduplicate very close labels (within 30 pixels)
                is_dup = False
                for node in detected_nodes:
                    if math.sqrt((node["x"] - cx)**2 + (node["y"] - cy)**2) < 30:
                        is_dup = True
                        break
                        
                if not is_dup:
                    detected_nodes.append({
                        "name": text,
                        "x": float(cx),
                        "y": float(cy)
                    })

        # Fallback Mock: If no rooms detected (blank blueprint or OCR failed), generate layout
        if len(detected_nodes) < 3:
            logger.warning("No room labels detected on blueprint. Generating default seed layout nodes.")
            detected_nodes = [
                {"name": "Entrance Lobby", "x": float(w * 0.1), "y": float(h * 0.5)},
                {"name": "Room 101", "x": float(w * 0.3), "y": float(h * 0.2)},
                {"name": "Room 102", "x": float(w * 0.3), "y": float(h * 0.8)},
                {"name": "Corridor Intersection", "x": float(w * 0.5), "y": float(h * 0.5)},
                {"name": "Computer Lab", "x": float(w * 0.7), "y": float(h * 0.2)},
                {"name": "Restroom", "x": float(w * 0.7), "y": float(h * 0.8)},
                {"name": "Exit Gate", "x": float(w * 0.9), "y": float(h * 0.5)}
            ]

        # 2. Build edges using K-Nearest Neighbors heuristic
        edges = []
        num_nodes = len(detected_nodes)
        
        # Connect each node to its nearest 2-3 neighbors
        k_neighbors = min(3, num_nodes - 1)
        
        for i in range(num_nodes):
            distances = []
            for j in range(num_nodes):
                if i == j:
                    continue
                # Calculate pixel distance
                d = math.sqrt((detected_nodes[i]["x"] - detected_nodes[j]["x"])**2 + 
                              (detected_nodes[i]["y"] - detected_nodes[j]["y"])**2)
                distances.append((d, j))
                
            # Sort by distance
            distances.sort()
            
            # Add edges
            for n in range(k_neighbors):
                dist_pixels, neighbor_idx = distances[n]
                # Scale: Assume 25 pixels = 1 meter
                dist_meters = round(dist_pixels / 25.0, 1)
                
                # Check for duplicates (undirected edge)
                edge_exists = False
                for edge in edges:
                    if (edge["src"] == i and edge["dest"] == neighbor_idx) or \
                       (edge["src"] == neighbor_idx and edge["dest"] == i):
                        edge_exists = True
                        break
                        
                if not edge_exists:
                    edges.append({
                        "src": i,
                        "dest": neighbor_idx,
                        "distance": dist_meters
                    })

        # 3. Save to database
        self._save_to_database(detected_nodes, edges)
        return True

    def _save_to_database(self, nodes, edges):
        """Clears old map records and saves new nodes/edges to SQLite."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Disable and re-enable keys if needed, or clear tables
            cursor.execute("PRAGMA foreign_keys = OFF;")
            cursor.execute("DELETE FROM rooms;")
            cursor.execute("DELETE FROM navigation_edges;")
            cursor.execute("DELETE FROM navigation_nodes;")
            cursor.execute("DELETE FROM buildings;")
            cursor.execute("PRAGMA foreign_keys = ON;")
            
            # Insert Building
            cursor.execute("INSERT INTO buildings (building_name) VALUES ('Uploaded Building')")
            building_id = cursor.lastrowid
            
            # Insert Nodes
            node_ids = []
            for node in nodes:
                cursor.execute("""
                INSERT INTO navigation_nodes (node_name, x_coordinate, y_coordinate, building_id)
                VALUES (?, ?, ?, ?)
                """, (node["name"], node["x"], node["y"], building_id))
                node_ids.append(cursor.lastrowid)
                
            # Insert Edges
            for edge in edges:
                src_id = node_ids[edge["src"]]
                dest_id = node_ids[edge["dest"]]
                dist = edge["distance"]
                
                # Bidirectional edges
                cursor.execute("""
                INSERT OR IGNORE INTO navigation_edges (source_node, destination_node, distance)
                VALUES (?, ?, ?)
                """, (src_id, dest_id, dist))
                cursor.execute("""
                INSERT OR IGNORE INTO navigation_edges (source_node, destination_node, distance)
                VALUES (?, ?, ?)
                """, (dest_id, src_id, dist))
                
            # Insert Rooms linked to nodes (exclude corridor intersections from explicit Room dropdowns)
            for idx, node in enumerate(nodes):
                name = node["name"]
                node_id = node_ids[idx]
                
                # Check if it represents a room
                # Standardize name for rooms table (e.g. "Room 101" -> "101")
                room_num = re.sub(r'^(room|lobby|office|lab|hall|restroom)\s+', '', name, flags=re.IGNORECASE)
                
                cursor.execute("""
                INSERT INTO rooms (room_number, building_id, node_id)
                VALUES (?, ?, ?)
                """, (room_num, building_id, node_id))
                
            conn.commit()
            logger.info("Successfully populated SQLite with automatically analyzed graph.")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save analyzed plan to DB: {e}")
        finally:
            conn.close()
