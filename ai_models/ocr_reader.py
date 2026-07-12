import re
import cv2
import logging
from database.db_helper import get_db_connection

logger = logging.getLogger(__name__)

class OCRReader:
    def __init__(self):
        self.reader = None
        self.ocr_loaded = False
        self.load_reader()

    def load_reader(self):
        try:
            import easyocr
            logger.info("Initializing EasyOCR reader (English)...")
            # This may download model files on first run to ~/.EasyOCR/
            self.reader = easyocr.Reader(['en'], gpu=False) # CPU by default for stability
            self.ocr_loaded = True
            logger.info("EasyOCR initialized successfully.")
        except Exception as e:
            logger.warning(f"Could not load EasyOCR: {e}. OCR will run in simulation/mock mode.")
            self.reader = None
            self.ocr_loaded = False

    def save_recognized_location(self, text):
        """Saves recognized text to database for history/status logging."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO recognized_locations (detected_text) VALUES (?)",
                (text,)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error saving recognized location to DB: {e}")

    def clean_text(self, text):
        """Cleans extracted text, removing extra spaces and special chars."""
        # Strip and remove redundant non-alphanumeric except rooms/hyphens
        cleaned = re.sub(r'[^a-zA-Z0-9\s\-]', '', text)
        return cleaned.strip()

    def extract_text(self, frame):
        """
        Runs OCR on the given frame image.
        Returns:
            results: list of dicts with: text, confidence, bbox
        """
        ocr_results = []
        if not self.ocr_loaded or self.reader is None:
            # Fallback mock OCR simulation:
            # If the user is running a demo and we have frames,
            # we can look for high contrast regions and mock room labels
            # to make the application responsive.
            return ocr_results
            
        try:
            # Convert frame to RGB for EasyOCR
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Run EasyOCR readtext
            raw_results = self.reader.readtext(rgb_frame)
            
            for (bbox, text, prob) in raw_results:
                if prob < 0.35: # Confidence threshold
                    continue
                    
                cleaned = self.clean_text(text)
                if len(cleaned) < 2:
                    continue
                    
                # Format bbox as standard [x1, y1, x2, y2]
                # EasyOCR returns bbox as list of 4 points: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                x_coords = [point[0] for point in bbox]
                y_coords = [point[1] for point in bbox]
                formatted_bbox = [int(min(x_coords)), int(min(y_coords)), int(max(x_coords)), int(max(y_coords))]
                
                ocr_results.append({
                    "text": cleaned,
                    "confidence": float(prob),
                    "bbox": formatted_bbox
                })
                
                # Check if it looks like a room number or department and save it
                if re.search(r'\b(room|lobby|exit|office|lab|hall|stairs|\d{3})\b', cleaned.lower()):
                    self.save_recognized_location(cleaned)
                    
        except Exception as e:
            logger.error(f"Error processing EasyOCR frame: {e}")
            
        return ocr_results
