import sqlite3
import os
from config import Config

def get_db_connection():
    db_path = Config.DATABASE_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Create Buildings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS buildings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        building_name TEXT NOT NULL UNIQUE
    );
    """)
    
    # Create NavigationNodes table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS navigation_nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_name TEXT NOT NULL UNIQUE,
        x_coordinate REAL NOT NULL,
        y_coordinate REAL NOT NULL,
        building_id INTEGER NOT NULL,
        FOREIGN KEY(building_id) REFERENCES buildings(id) ON DELETE CASCADE
    );
    """)
    
    # Create Rooms table (linked to building and node)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_number TEXT NOT NULL,
        building_id INTEGER NOT NULL,
        node_id INTEGER,
        FOREIGN KEY(building_id) REFERENCES buildings(id) ON DELETE CASCADE,
        FOREIGN KEY(node_id) REFERENCES navigation_nodes(id) ON DELETE SET NULL
    );
    """)
    
    # Create NavigationEdges table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS navigation_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_node INTEGER NOT NULL,
        destination_node INTEGER NOT NULL,
        distance REAL NOT NULL,
        FOREIGN KEY(source_node) REFERENCES navigation_nodes(id) ON DELETE CASCADE,
        FOREIGN KEY(destination_node) REFERENCES navigation_nodes(id) ON DELETE CASCADE,
        UNIQUE(source_node, destination_node)
    );
    """)
    
    # Create RecognizedLocations table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recognized_locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        detected_text TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    conn.commit()
    conn.close()

def seed_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if building already exists
    cursor.execute("SELECT id FROM buildings WHERE building_name = 'Main Engineering Block'")
    row = cursor.fetchone()
    if row:
        conn.close()
        return  # Already seeded
    
    # 1. Insert Building
    cursor.execute("INSERT INTO buildings (building_name) VALUES ('Main Engineering Block')")
    building_id = cursor.lastrowid
    
    # 2. Insert Navigation Nodes
    nodes = [
        # (name, x, y, building_id)
        ("Entrance Lobby", 0.0, 0.0, building_id),          # ID: 1
        ("Corridor A - South", 0.0, 10.0, building_id),      # ID: 2
        ("Corridor A - Mid", 0.0, 20.0, building_id),        # ID: 3
        ("Corridor A - North", 0.0, 30.0, building_id),      # ID: 4
        ("Dean's Office Door", 5.0, 10.0, building_id),      # ID: 5
        ("Computer Lab Entrance", -5.0, 20.0, building_id),  # ID: 6
        ("Restroom Entrance", 5.0, 20.0, building_id),       # ID: 7
        ("Seminar Hall Entrance", -5.0, 30.0, building_id),  # ID: 8
        ("Staircase Landing", 0.0, 40.0, building_id),       # ID: 9
        ("Exit Gate", 0.0, -5.0, building_id)                # ID: 10
    ]
    cursor.executemany("""
    INSERT INTO navigation_nodes (node_name, x_coordinate, y_coordinate, building_id)
    VALUES (?, ?, ?, ?)
    """, nodes)
    
    # Get IDs of inserted nodes for linking
    cursor.execute("SELECT id, node_name FROM navigation_nodes")
    node_map = {row['node_name']: row['id'] for row in cursor.fetchall()}
    
    # 3. Insert Rooms
    rooms = [
        # (room_number, building_id, node_id)
        ("Lobby", building_id, node_map["Entrance Lobby"]),
        ("101", building_id, node_map["Entrance Lobby"]),
        ("102", building_id, node_map["Dean's Office Door"]),
        ("103", building_id, node_map["Computer Lab Entrance"]),
        ("104", building_id, node_map["Restroom Entrance"]),
        ("105", building_id, node_map["Seminar Hall Entrance"]),
        ("Exit", building_id, node_map["Exit Gate"]),
        ("Stairs", building_id, node_map["Staircase Landing"])
    ]
    cursor.executemany("""
    INSERT INTO rooms (room_number, building_id, node_id)
    VALUES (?, ?, ?)
    """, rooms)
    
    # 4. Insert Navigation Edges (Bidirectional connections, so we insert both ways)
    edges = [
        # (src, dest, distance)
        # Main corridor spine
        ("Entrance Lobby", "Corridor A - South", 10.0),
        ("Corridor A - South", "Corridor A - Mid", 10.0),
        ("Corridor A - Mid", "Corridor A - North", 10.0),
        ("Corridor A - North", "Staircase Landing", 10.0),
        ("Entrance Lobby", "Exit Gate", 5.0),
        
        # Off-spine rooms/doors
        ("Corridor A - South", "Dean's Office Door", 5.0),
        ("Corridor A - Mid", "Computer Lab Entrance", 5.0),
        ("Corridor A - Mid", "Restroom Entrance", 5.0),
        ("Corridor A - North", "Seminar Hall Entrance", 5.0)
    ]
    
    edges_to_insert = []
    for src_name, dest_name, dist in edges:
        src_id = node_map[src_name]
        dest_id = node_map[dest_name]
        # Forward edge
        edges_to_insert.append((src_id, dest_id, dist))
        # Reverse edge (bidirectional)
        edges_to_insert.append((dest_id, src_id, dist))
        
    cursor.executemany("""
    INSERT OR IGNORE INTO navigation_edges (source_node, destination_node, distance)
    VALUES (?, ?, ?)
    """, edges_to_insert)
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    seed_data()
    print("Database initialized and seeded.")
