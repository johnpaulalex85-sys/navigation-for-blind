import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'aiden_secret_key_13579')
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Database
    DATABASE_PATH = os.path.join(BASE_DIR, 'database', 'aiden.db')
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
    
    # Uploads
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload size
    
    # AI Weights
    WEIGHTS_DIR = os.path.join(BASE_DIR, 'weights')
    YOLO_MODEL_PATH = os.path.join(WEIGHTS_DIR, 'yolo11n.pt')
    WHISPER_MODEL_NAME = "tiny"  # 'tiny', 'base', 'small', 'medium'
    
    # App Settings
    DEBUG = os.environ.get('FLASK_DEBUG', 'True') == 'True'
    HOST = '0.0.0.0'
    PORT = 5000
