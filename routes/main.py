import os
import uuid
import base64
import cv2
import numpy as np
import logging
from flask import Blueprint, render_template, request, jsonify
from werkzeug.utils import secure_filename

from config import Config
from database.db_helper import get_db_connection
from ai_models.yolo_detector import YOLODetector
from ai_models.ocr_reader import OCRReader
from ai_models.whisper_engine import WhisperEngine
from ai_models.navigation_engine import NavigationEngine
from ai_models.blueprint_analyzer import BlueprintAnalyzer

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)

# Global instances (lazy loaded)
_detector = None
_ocr = None
_whisper = None
_analyzer = None

def get_detector():
    global _detector
    if _detector is None:
        _detector = YOLODetector()
    return _detector

def get_ocr():
    global _ocr
    if _ocr is None:
        _ocr = OCRReader()
    return _ocr

def get_whisper():
    global _whisper
    if _whisper is None:
        _whisper = WhisperEngine()
    return _whisper

def get_analyzer():
    global _analyzer
    if _analyzer is None:
        _analyzer = BlueprintAnalyzer()
    return _analyzer

# Helper: Convert base64 data URL to OpenCV image
def base64_to_cv2(base64_string):
    try:
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        img_data = base64.b64decode(base64_string)
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        logger.error(f"Error decoding base64 image: {e}")
        return None

# --- HTML Page Routes ---

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/navigation')
def navigation():
    return render_template('navigation.html')

@main_bp.route('/status')
def status():
    detector = get_detector()
    ocr = get_ocr()
    whisper = get_whisper()
    
    db_ok = False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        db_ok = True
        conn.close()
    except Exception as e:
        logger.error(f"DB Status Check Failed: {e}")
        
    return jsonify({
        "status": "healthy" if db_ok else "unhealthy",
        "database": "connected" if db_ok else "disconnected",
        "yolo_model": "loaded" if detector.model_loaded else "fallback_opencv",
        "ocr_model": "loaded" if ocr.ocr_loaded else "fallback_simulation",
        "whisper_model": "loaded" if whisper.whisper_loaded else "fallback_api"
    })

# --- Blueprint Upload and Automatic Analysis ---

@main_bp.route('/api/analyze-blueprint', methods=['POST'])
def analyze_blueprint():
    if 'blueprint' not in request.files:
        return jsonify({"error": "No blueprint file provided"}), 400
        
    file = request.files['blueprint']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
        
    try:
        # Save file to uploads folder
        filename = "floor_plan.png" # Fixed name for navigation dashboard reference
        filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        file.save(filepath)
        
        # Analyze file
        success = get_analyzer().analyze(filepath)
        if not success:
            return jsonify({"error": "Blueprint analysis failed"}), 500
            
        # Fetch newly created rooms and nodes
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT r.id, r.room_number, n.node_name, n.x_coordinate, n.y_coordinate FROM rooms r JOIN navigation_nodes n ON r.node_id = n.id")
        rooms = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT * FROM navigation_nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT * FROM navigation_edges")
        edges = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return jsonify({
            "message": "Blueprint analyzed successfully.",
            "map_url": f"/static/uploads/{filename}",
            "rooms": rooms,
            "nodes": nodes,
            "edges": edges
        })
    except Exception as e:
        logger.error(f"Error during blueprint analysis route: {e}")
        return jsonify({"error": str(e)}), 500

# --- Public API Endpoints ---

@main_bp.route('/api/rooms', methods=['GET'])
def get_rooms():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT r.id, r.room_number, n.node_name 
        FROM rooms r 
        JOIN navigation_nodes n ON r.node_id = n.id
        """)
        rooms = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(rooms)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@main_bp.route('/api/nodes', methods=['GET'])
def get_nodes():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, node_name, x_coordinate, y_coordinate FROM navigation_nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(nodes)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@main_bp.route('/api/edges', methods=['GET'])
def get_edges():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT source_node, destination_node, distance FROM navigation_edges")
        edges = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(edges)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- REST AI Endpoints ---

@main_bp.route('/detect', methods=['POST'])
def detect():
    data = request.json
    if not data or 'image' not in data:
        return jsonify({"error": "No image data provided"}), 400
        
    img = base64_to_cv2(data['image'])
    if img is None:
        return jsonify({"error": "Invalid image encoding"}), 400
        
    detections, alerts = get_detector().process_frame(img)
    return jsonify({
        "detections": detections,
        "alerts": alerts
    })

@main_bp.route('/ocr', methods=['POST'])
def ocr():
    data = request.json
    if not data or 'image' not in data:
        return jsonify({"error": "No image data provided"}), 400
        
    img = base64_to_cv2(data['image'])
    if img is None:
        return jsonify({"error": "Invalid image encoding"}), 400
        
    ocr_results = get_ocr().extract_text(img)
    return jsonify({
        "ocr_results": ocr_results
    })

@main_bp.route('/voice-command', methods=['POST'])
def voice_command():
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
        
    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({"error": "Empty audio file name"}), 400
        
    temp_dir = os.path.join(Config.BASE_DIR, 'static', 'uploads', 'audio')
    os.makedirs(temp_dir, exist_ok=True)
    
    filename = secure_filename(f"{uuid.uuid4()}_{audio_file.filename}")
    filepath = os.path.join(temp_dir, filename)
    audio_file.save(filepath)
    
    try:
        transcription = get_whisper().transcribe_audio(filepath)
        parsed = get_whisper().parse_command(transcription)
        
        if os.path.exists(filepath):
            os.remove(filepath)
            
        return jsonify({
            "transcription": transcription,
            "command": parsed["command"],
            "target": parsed.get("target"),
            "raw_parsed": parsed
        })
    except Exception as e:
        logger.error(f"Error processing voice command: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"error": str(e)}), 500

@main_bp.route('/navigate', methods=['POST'])
def navigate():
    data = request.json or {}
    source = data.get('source')
    destination = data.get('destination')
    
    if not source or not destination:
        return jsonify({"error": "Source and destination are required"}), 400
        
    src_node_id = NavigationEngine.get_room_node_id(source)
    dest_node_id = NavigationEngine.get_room_node_id(destination)
    
    if not src_node_id:
        return jsonify({"error": f"Could not resolve source location: '{source}'"}), 404
    if not dest_node_id:
        return jsonify({"error": f"Could not resolve destination location: '{destination}'"}), 404
        
    path, total_dist = NavigationEngine.a_star(src_node_id, dest_node_id)
    
    if not path:
        return jsonify({"error": "No route found between selected points."}), 404
        
    instructions = NavigationEngine.generate_directions(path)
    
    return jsonify({
        "source_node": path[0],
        "destination_node": path[-1],
        "path": path,
        "total_distance": round(total_dist, 1),
        "instructions": instructions
    })
