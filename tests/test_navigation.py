import unittest
import sys
import os

# Set python path to find config and modules properly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.db_helper import init_db, seed_data, get_db_connection
from ai_models.navigation_engine import NavigationEngine
from ai_models.blueprint_analyzer import BlueprintAnalyzer

class TestNavigationEngine(unittest.TestCase):
    def setUp(self):
        # Set up SQLite database fresh for each test case by deleting the DB file
        from config import Config
        db_path = Config.DATABASE_PATH
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass
        init_db()
        seed_data()

    def test_room_node_resolution(self):
        # Verify room matching matches correct nodes
        node_id = NavigationEngine.get_room_node_id("102")
        self.assertIsNotNone(node_id, "Should resolve room 102 to a node ID.")
        
        # Test fuzzy matching
        node_id_fuzzy = NavigationEngine.get_room_node_id("computer lab")
        self.assertIsNotNone(node_id_fuzzy, "Should fuzzy resolve 'computer lab' node.")

    def test_a_star_pathfind(self):
        # Test routing between Entrance Lobby and Dean's Office
        src_id = NavigationEngine.get_room_node_id("Entrance Lobby")
        dest_id = NavigationEngine.get_room_node_id("102")
        
        path, total_dist = NavigationEngine.a_star(src_id, dest_id)
        
        self.assertIsNotNone(path, "A* path planning should find a valid route.")
        self.assertEqual(len(path), 3, "Path should contain 3 nodes.")
        self.assertEqual(total_dist, 15.0, "Total route distance should equal 15.0 meters.")

    def test_direction_generation(self):
        src_id = NavigationEngine.get_room_node_id("Entrance Lobby")
        dest_id = NavigationEngine.get_room_node_id("102")
        path, _ = NavigationEngine.a_star(src_id, dest_id)
        
        instructions = NavigationEngine.generate_directions(path)
        
        self.assertTrue(len(instructions) >= 2, "Should generate starting and ending instructions.")
        self.assertIn("Start from Entrance Lobby", instructions[0], "First instruction should guide starting point.")
        self.assertIn("Turn right", instructions[1], "Second instruction should contain relative turn instruction.")

    def test_blueprint_analyzer_fallback(self):
        # Initialize analyzer
        analyzer = BlueprintAnalyzer()
        
        # Call analyze with a dummy file path (triggering fallback)
        success = analyzer.analyze("non_existent_image.png")
        self.assertTrue(success, "Analyzer should succeed via automatic fallback layout on failure to load file.")
        
        # Check that nodes are registered in the database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM navigation_nodes")
        node_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM navigation_edges")
        edge_count = cursor.fetchone()[0]
        conn.close()
        
        # Fallback seeds 7 nodes
        self.assertEqual(node_count, 7, "Fallback layout should create 7 navigation nodes.")
        self.assertTrue(edge_count > 0, "Fallback layout should automatically connect nodes with edges.")
        
        # Verify we can plan a route on this automatically generated blueprint graph
        src_id = NavigationEngine.get_room_node_id("Entrance Lobby")
        dest_id = NavigationEngine.get_room_node_id("102") # Room 102 in fallback
        
        path, dist = NavigationEngine.a_star(src_id, dest_id)
        self.assertIsNotNone(path, "Should calculate valid route on analyzed blueprint graph.")
        self.assertTrue(dist > 0.0, "Calculated route distance should be positive.")

if __name__ == '__main__':
    unittest.main()
