import cv2
import numpy as np
import os
import logging
from config import Config

# Initialize logger
logger = logging.getLogger(__name__)

class YOLODetector:
    def __init__(self):
        self.model = None
        self.model_loaded = False
        self.weights_path = Config.YOLO_MODEL_PATH
        
        # Mapping COCO class IDs to target classes
        # COCO IDs: 0: person, 56: chair, 60: dining table
        self.coco_mapping = {
            0: "Person",
            56: "Chair",
            60: "Table"
        }
        
        # Approximate real-world heights (in meters) for distance estimation
        self.class_heights = {
            "Person": 1.7,
            "Chair": 0.8,
            "Table": 0.75,
            "Door": 2.0,
            "Stairs": 1.2,
            "Wall": 2.5,
            "Elevator": 2.1,
            "Exit Sign": 0.3
        }
        
        # Empirical focal length constant: distance = (real_height * focal_constant) / box_height
        self.focal_constant = 400.0 
        
        self.load_model()

    def load_model(self):
        try:
            # Ensure weights folder exists
            os.makedirs(os.path.dirname(self.weights_path), exist_ok=True)
            
            # Import YOLO from ultralytics
            from ultralytics import YOLO
            
            # Load model
            logger.info(f"Loading YOLOv11 from {self.weights_path}...")
            self.model = YOLO(self.weights_path)
            self.model_loaded = True
            logger.info("YOLOv11 model loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not load YOLOv11: {e}. Falling back to OpenCV CV-heuristics & simulation mode.")
            self.model = None
            self.model_loaded = False

    def estimate_distance_and_position(self, bbox, class_name, frame_w, frame_h):
        """
        Estimates distance based on bbox height and positioning relative to screen center.
        bbox: [x1, y1, x2, y2]
        """
        x1, y1, x2, y2 = bbox
        box_w = x2 - x1
        box_h = y2 - y1
        
        # Avoid division by zero
        if box_h == 0:
            box_h = 1
            
        real_height = self.class_heights.get(class_name, 1.0)
        distance = (real_height * self.focal_constant) / box_h
        distance = round(max(0.5, min(distance, 15.0)), 1) # Limit distance to realistic 0.5m - 15m
        
        # Position mapping
        box_center_x = x1 + (box_w / 2.0)
        left_bound = frame_w * 0.35
        right_bound = frame_w * 0.65
        
        if box_center_x < left_bound:
            position = "left"
        elif box_center_x > right_bound:
            position = "right"
        else:
            position = "center"
            
        return distance, position

    def detect_heuristics_opencv(self, frame, detections):
        """
        OpenCV image processing algorithms to detect Door, Stairs, Exit Sign, Walls
        when standard COCO weights don't support them.
        """
        h, w, _ = frame.shape
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 1. Stairs Detection (Horizontal parallel lines)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=80, minLineLength=w//3, maxLineGap=15)
        
        horizontal_lines = 0
        stairs_y = []
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                # Check if line is close to horizontal
                if abs(y2 - y1) < 5:
                    horizontal_lines += 1
                    stairs_y.append(y1)
                    
        # If multiple horizontal lines are stacked vertically, it is likely stairs
        if horizontal_lines >= 4:
            y_min, y_max = min(stairs_y), max(stairs_y)
            # Find horizontal bounding region
            stairs_bbox = [int(w*0.1), int(y_min), int(w*0.9), int(y_max)]
            dist, pos = self.estimate_distance_and_position(stairs_bbox, "Stairs", w, h)
            detections.append({
                "class": "Stairs",
                "confidence": 0.70,
                "bbox": stairs_bbox,
                "distance": dist,
                "position": pos
            })

        # 2. Exit Sign Detection (Green rectangular shapes)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        # Green range for exit signs
        lower_green = np.array([35, 40, 40])
        upper_green = np.array([85, 255, 255])
        green_mask = cv2.inRange(hsv, lower_green, upper_green)
        green_contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in green_contours:
            area = cv2.contourArea(contour)
            if area > 800: # Threshold for size
                x, y, box_w, box_h = cv2.boundingRect(contour)
                aspect_ratio = float(box_w) / box_h
                # Exit signs are horizontal rectangles (usually 1.5 - 3.0 aspect ratio)
                if 1.2 < aspect_ratio < 3.5:
                    exit_bbox = [int(x), int(y), int(x + box_w), int(y + box_h)]
                    dist, pos = self.estimate_distance_and_position(exit_bbox, "Exit Sign", w, h)
                    detections.append({
                        "class": "Exit Sign",
                        "confidence": 0.85,
                        "bbox": exit_bbox,
                        "distance": dist,
                        "position": pos
                    })
                    break # Usually only one exit sign in focus

        # 3. Door detection (Vertical rectangles with door aspect ratios)
        # We look for door-sized contours or gaps in walls
        # Use bilateral filter to preserve edges, then Canny
        blur = cv2.bilateralFilter(gray, 9, 75, 75)
        door_edges = cv2.Canny(blur, 30, 100)
        contours, _ = cv2.findContours(door_edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.04 * perimeter, True)
            # Doors are rectangles (4 vertices)
            if len(approx) == 4:
                x, y, box_w, box_h = cv2.boundingRect(approx)
                aspect_ratio = float(box_h) / max(1, box_w)
                # Door is vertical (aspect ratio between 1.5 and 2.5) and takes a good portion of height
                if 1.5 < aspect_ratio < 3.0 and box_h > h * 0.35:
                    # Avoid overlapping with exit signs
                    door_bbox = [int(x), int(y), int(x + box_w), int(y + box_h)]
                    dist, pos = self.estimate_distance_and_position(door_bbox, "Door", w, h)
                    detections.append({
                        "class": "Door",
                        "confidence": 0.65,
                        "bbox": door_bbox,
                        "distance": dist,
                        "position": pos
                    })
                    break

        # 4. Wall Detection (Large contours on sides)
        # If there are strong vertical edges right near the boundary of the frame
        left_edges = edges[:, :int(w*0.15)]
        right_edges = edges[:, int(w*0.85):]
        if np.sum(left_edges > 0) > (h * 1.5) or np.sum(right_edges > 0) > (h * 1.5):
            # Wall detected very close to sides
            wall_bbox = [0, 0, int(w), int(h)]
            detections.append({
                "class": "Wall",
                "confidence": 0.60,
                "bbox": wall_bbox,
                "distance": 1.0,
                "position": "center"
            })

    def process_frame(self, frame):
        """
        Runs object detection on the input frame.
        Returns:
            detections: List of dicts with: class, confidence, bbox, distance, position
            alerts: List of critical warning strings
        """
        h, w, _ = frame.shape
        detections = []
        alerts = []
        
        if self.model_loaded and self.model is not None:
            try:
                # Run inference
                results = self.model(frame, verbose=False)
                for result in results:
                    boxes = result.boxes
                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        conf = float(box.conf[0].item())
                        
                        if conf < 0.40:
                            continue
                            
                        # Map to our target subset classes if present in COCO
                        class_name = self.coco_mapping.get(cls_id, None)
                        if class_name:
                            bbox = box.xyxy[0].tolist() # [x1, y1, x2, y2]
                            bbox = [int(val) for val in bbox]
                            
                            dist, pos = self.estimate_distance_and_position(bbox, class_name, w, h)
                            
                            detections.append({
                                "class": class_name,
                                "confidence": conf,
                                "bbox": bbox,
                                "distance": dist,
                                "position": pos
                            })
            except Exception as e:
                logger.error(f"Error in YOLO inference: {e}")
                
        # Run custom OpenCV heuristics to detect custom classes
        self.detect_heuristics_opencv(frame, detections)
        
        # Generate Navigation / Warning Alerts
        for det in detections:
            c_name = det["class"]
            dist = det["distance"]
            pos = det["position"]
            
            # Formulate alert text
            # Person alert
            if c_name == "Person":
                if dist <= 2.0:
                    if pos == "center":
                        alerts.append("Person approaching ahead. Watch out.")
                    else:
                        alerts.append(f"Person approaching on your {pos}.")
            
            # Obstacles
            elif c_name in ["Chair", "Table", "Stairs", "Door"]:
                if dist <= 2.0:
                    if pos == "center":
                        alerts.append(f"{c_name} detected {dist} meters straight ahead.")
                    else:
                        alerts.append(f"{c_name} detected {dist} meters on your {pos}.")
                        
            # Critical Danger Warnings
            elif c_name == "Wall" and dist <= 1.0:
                alerts.append("Close to wall. Adjust direction.")
                
            elif c_name == "Exit Sign":
                alerts.append(f"Exit sign detected {dist} meters ahead.")

        return detections, alerts
