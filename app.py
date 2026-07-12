import os
import logging
from flask import Flask
from flask_socketio import SocketIO, emit

from config import Config
from database.db_helper import init_db, seed_data
from routes.main import main_bp, get_detector, get_ocr, base64_to_cv2

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize database
logger.info("Initializing and seeding database...")
init_db()
seed_data()

# Create Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Register main blueprint
app.register_blueprint(main_bp)

# Initialize Flask-SocketIO
# simple-websocket is installed, so we can use standard threading/gevent/eventlet
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=None)

# Store frame counters per session for OCR throttling
session_frame_counters = {}

# --- WebSocket Event Handlers ---

@socketio.on('connect')
def handle_connect():
    session_id = getattr(request, 'sid', 'unknown_sid')
    session_frame_counters[session_id] = 0
    logger.info(f"Client connected: {session_id}")
    emit('status_update', {'message': 'Connected to AIDEN server'})

@socketio.on('disconnect')
def handle_disconnect():
    session_id = getattr(request, 'sid', 'unknown_sid')
    if session_id in session_frame_counters:
        del session_frame_counters[session_id]
    logger.info(f"Client disconnected: {session_id}")

@socketio.on('video_frame')
def handle_video_frame(data):
    session_id = getattr(request, 'sid', 'unknown_sid')
    if not data or 'image' not in data:
        return
        
    img_b64 = data['image']
    img = base64_to_cv2(img_b64)
    if img is None:
        return
        
    # Increment frame counter for session
    if session_id not in session_frame_counters:
        session_frame_counters[session_id] = 0
    session_frame_counters[session_id] += 1
    frame_count = session_frame_counters[session_id]
    
    # 1. Run YOLO Object Detection (every frame)
    detections, alerts = get_detector().process_frame(img)
    
    # 2. Run OCR Detection (throttled every 10 frames to avoid CPU lag)
    ocr_detections = []
    if frame_count % 10 == 0:
        ocr_detections = get_ocr().extract_text(img)
        # If text is detected, emit OCR update
        if ocr_detections:
            emit('ocr_detection', {'ocr': ocr_detections})
            
            # Auto-save OCR text detections that represent locations to database
            # already handled inside ocr_reader.py
            
    # 3. Emit object detections and warnings
    emit('object_detection', {
        'detections': detections,
        'alerts': alerts
    })
    
    # 4. Trigger voice alert if critical safety warnings exist
    if alerts:
        emit('voice_alert', {'alert': alerts[0]}) # Broadcast top priority warning

@socketio.on('navigation_update')
def handle_navigation_update(data):
    """
    Receives current location and target destination names.
    Calculates shortest path using A* and emits route details.
    """
    from ai_models.navigation_engine import NavigationEngine
    
    source = data.get('source')
    destination = data.get('destination')
    
    if not source or not destination:
        emit('navigation_error', {'error': 'Missing parameters'})
        return
        
    src_node_id = NavigationEngine.get_room_node_id(source)
    dest_node_id = NavigationEngine.get_room_node_id(destination)
    
    if not src_node_id or not dest_node_id:
        emit('navigation_error', {'error': 'Invalid source or destination'})
        return
        
    path, total_dist = NavigationEngine.a_star(src_node_id, dest_node_id)
    if path:
        instructions = NavigationEngine.generate_directions(path)
        emit('navigation_route', {
            'path': path,
            'total_distance': total_dist,
            'instructions': instructions
        })
    else:
        emit('navigation_error', {'error': 'Route not found'})

if __name__ == '__main__':
    # Start server
    logger.info(f"Starting AIDEN server on {Config.HOST}:{Config.PORT}...")
    socketio.run(app, host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
