import json
import math
from collections import deque
from pathlib import Path
import cv2
import numpy as np
from ultralytics import YOLO
import easyocr
import re

class ViolationDetector:
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent
        self.config_path = self.base_dir / "config.json"
        self.config = self._load_config()

        self.speed_limit_kmh = self.config.get("speed_limit_kmh", 60)
        
        # Load YOLOv8 nano model
        self.yolo_model = YOLO("yolov8n.pt")
        self.yolo_names = self.yolo_model.names

        print("Loading OCR Engine (First boot takes a few seconds)...")
        self.reader = easyocr.Reader(['en'], gpu=False)

        self.has_pose = False

        # Unified System Memory
        self.frame_count = 0
        self.fps = 30.0 # Standard video FPS for math
        self.tracked_vehicles = {} # Stores memory of where cars have been
        
        # Speed Calibration Zone (Pixels -> Meters)
        self.line_start_y = 250
        self.line_end_y = 450
        self.zone_distance_meters = 25.0 

        self.frame_buffer = deque(maxlen=30)
        self.helmet_frame_counter = 0
        self.violation_latch_frames = 0
        self.active_violations = []
        self.last_plate = "UNKNOWN"

    def _load_config(self):
        default_config = {"speed_limit_kmh": 60, "fines": {"helmet": 1000, "speed": 2000}}
        if not self.config_path.exists(): return default_config
        with open(self.config_path, "r", encoding="utf-8") as file: return json.load(file)

    def _get_yolo_detections(self, yolo_results):
        detections = []
        if yolo_results is None or yolo_results.boxes is None: return detections
        for box in yolo_results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
            
            # Extract tracking ID if available
            track_id = int(box.id[0]) if box.id is not None else -1
            
            detections.append({
                "class_id": cls_id, "class_name": self.yolo_names.get(cls_id, str(cls_id)),
                "confidence": conf, "box": [x1, y1, x2, y2], "track_id": track_id
            })
        return detections

    def check_frame_for_no_helmet(self, frame, detections):
        person_detections = [d for d in detections if d["class_name"] == "person" and d["confidence"] >= 0.45]
        motorcycles = [d for d in detections if d["class_name"] == "motorcycle"]
        
        if not person_detections: return False, None
        frame_height, frame_width = frame.shape[:2]
        
        for person in person_detections:
            px1, py1, px2, py2 = person["box"]
            person_area = max(1, (px2 - px1) * (py2 - py1))
            
            is_riding = False
            for moto in motorcycles:
                mx1, my1, mx2, my2 = moto["box"]
                ix1, iy1 = max(px1, mx1), max(py1, my1)
                ix2, iy2 = min(px2, mx2), min(py2, my2)
                
                if ix1 < ix2 and iy1 < iy2:
                    if ((ix2 - ix1) * (iy2 - iy1) / person_area) > 0.15:
                        is_riding = True
                        break
                        
            if not is_riding: continue 

            px1, py1 = max(px1, 0), max(py1, 0)
            px2, py2 = min(px2, frame_width), min(py2, frame_height)
            person_height = py2 - py1
            if person_height <= 0: continue

            head_y2 = py1 + int(person_height * 0.25)
            head_crop = frame[py1:head_y2, px1:px2]
            if head_crop.size == 0: continue

            gray = cv2.cvtColor(head_crop, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 40, 120)
            edge_density = np.count_nonzero(edges) / edges.size

            _, threshold = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            helmet_shape = any(0.40 <= (4 * math.pi * cv2.contourArea(c) / (cv2.arcLength(c, True) ** 2)) <= 1.20 
                             for c in contours if cv2.contourArea(c) >= 60 and cv2.arcLength(c, True) > 0)
            
            mean_int = np.mean(gray)
            helmet_texture = edge_density > 0.055 or mean_int < 85 or mean_int > 175

            if not (helmet_shape and helmet_texture):
                return True, (px1, py1, px2, py2)
                
        return False, None

    def check_for_speeding(self, detections):
        speeding_vehicles = []
        target_classes = ["car", "truck", "bus", "motorcycle"]
        
        for d in detections:
            if d["class_name"] not in target_classes or d["track_id"] == -1: continue
            
            track_id = d["track_id"]
            x1, y1, x2, y2 = d["box"]
            center_y = (y1 + y2) // 2
            
            if track_id not in self.tracked_vehicles:
                self.tracked_vehicles[track_id] = {"start_frame": 0, "speed": 0, "ticketed": False}

            if self.line_start_y - 10 <= center_y <= self.line_start_y + 10:
                self.tracked_vehicles[track_id]["start_frame"] = self.frame_count
                
            elif self.line_end_y - 10 <= center_y <= self.line_end_y + 10:
                start_frame = self.tracked_vehicles[track_id]["start_frame"]
                if start_frame > 0 and not self.tracked_vehicles[track_id]["ticketed"]:
                    frames_passed = self.frame_count - start_frame
                    if frames_passed > 0:
                        time_seconds = frames_passed / self.fps
                        speed_ms = self.zone_distance_meters / time_seconds
                        speed_kmh = speed_ms * 3.6
                        
                        self.tracked_vehicles[track_id]["speed"] = speed_kmh
                        self.tracked_vehicles[track_id]["ticketed"] = True
                        
                        if speed_kmh > self.speed_limit_kmh:
                            speeding_vehicles.append((d, speed_kmh))
                            
        return speeding_vehicles

    def _scan_for_plate(self, image_crop):
        if image_crop.size == 0: return None
        ocr_results = self.reader.readtext(image_crop, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', contrast_ths=0.05, adjust_contrast=0.7, width_ths=0.7)
        raw_text = "".join([text for (bbox, text, prob) in ocr_results if prob > 0.1]).upper()
        clean_text = "".join(e for e in raw_text if e.isalnum())
        for word in ["GOODS", "CARRIER", "INDIA", "STOP", "HORN", "MAMTA", "TAX", "PERMIT"]: clean_text = clean_text.replace(word, "")
        match = re.search(r'([A-Z]{2}[0-9OIQ]{1,2}[A-Z]{0,3}[0-9OIQ]{3,4})', clean_text)
        if match: return match.group(1).replace('O', '0').replace('I', '1').replace('Q', '0')[:10]
        return None

    def extract_license_plate(self, frame, detections, target_box=None):
        vehicles = [d for d in detections if d["class_name"] in ["motorcycle", "car", "truck"]]
        if not vehicles: return "UNKNOWN"

        target_vehicle = None
        if target_box:
            px1, py1, px2, py2 = target_box
            best_overlap = 0
            for v in vehicles:
                vx1, vy1, vx2, vy2 = v["box"]
                ix1, iy1 = max(px1, vx1), max(py1, vy1)
                ix2, iy2 = min(px2, vx2), min(py2, vy2)
                if ix1 < ix2 and iy1 < iy2:
                    overlap = (ix2 - ix1) * (iy2 - iy1)
                    if overlap > best_overlap:
                        best_overlap = overlap
                        target_vehicle = v

        if not target_vehicle:
            vehicles.sort(key=lambda d: (d["box"][2]-d["box"][0])*(d["box"][3]-d["box"][1]), reverse=True)
            target_vehicle = vehicles[0]

        vx1, vy1, vx2, vy2 = target_vehicle["box"]
        vehicle_crop = frame[vy1:vy2, vx1:vx2]
        if vehicle_crop.size == 0: return "UNKNOWN"

        bumper_crop = frame[vy1 + int((vy2 - vy1) * 0.40):vy2, vx1:vx2]

        upscaled_bumper = cv2.resize(bumper_crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        if plate := self._scan_for_plate(upscaled_bumper): return plate

        gray_bumper = cv2.cvtColor(upscaled_bumper, cv2.COLOR_BGR2GRAY)
        if plate := self._scan_for_plate(cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(gray_bumper)): return plate

        upscaled_full = cv2.resize(vehicle_crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        if plate := self._scan_for_plate(upscaled_full): return plate

        return "UNKNOWN"

    def process_frame(self, frame):
        self.frame_count += 1
        result = {"violations": [], "confidence": {}, "boxes": [], "new_alert": False, "plate": "UNKNOWN", "fine_total": 0}
        if frame is None: return result

        # Enable YOLO Tracking Engine
        yolo_result = self.yolo_model.track(frame, persist=True, verbose=False)[0]
        detections = self._get_yolo_detections(yolo_result)
        result["boxes"] = [d["box"] for d in detections]

        current_frame_violations = []
        target_ocr_box = None

        # 1. Check for Helmets
        no_helmet_detected, helmet_violator_box = self.check_frame_for_no_helmet(frame, detections)
        if no_helmet_detected:
            self.helmet_frame_counter += 1
            if self.helmet_frame_counter >= 12:
                current_frame_violations.append("helmet")
                target_ocr_box = helmet_violator_box
        else:
            self.helmet_frame_counter = max(0, self.helmet_frame_counter - 1)

        # 2. Check for Speeding
        speeders = self.check_for_speeding(detections)
        for speeder_dict, speed_kmh in speeders:
            current_frame_violations.append("speed")
            target_ocr_box = speeder_dict["box"] # Snipe the speeding vehicle!
            cv2.putText(frame, f"SPEEDING: {int(speed_kmh)} km/h", (target_ocr_box[0], target_ocr_box[1] - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # Latch and OCR Logic
        if current_frame_violations:
            self.active_violations = current_frame_violations
            if self.violation_latch_frames == 0: 
                result["new_alert"] = True
                self.last_plate = self.extract_license_plate(frame, detections, target_ocr_box)
                print(f"🚨 OMNI-CAM CAUGHT VIOLATION ({', '.join(self.active_violations).upper()}) -> Plate: {self.last_plate}")
            self.violation_latch_frames = 20
        else:
            if self.violation_latch_frames > 0:
                self.violation_latch_frames -= 1
            else:
                self.active_violations = []

        result["plate"] = self.last_plate 
        if self.active_violations:
            result["violations"] = self.active_violations

        # UI Rendering
        cv2.line(frame, (0, self.line_start_y), (frame.shape[1], self.line_start_y), (0, 255, 255), 1)
        cv2.line(frame, (0, self.line_end_y), (frame.shape[1], self.line_end_y), (0, 255, 255), 2)
        cv2.putText(frame, "SPEED ZONE START", (10, self.line_start_y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        for detection in detections:
            # Render box if it's a vehicle or a person
            if detection["class_name"] in ["car", "truck", "bus", "motorcycle", "person"] and detection["confidence"] > 0.40:
                x1, y1, x2, y2 = detection["box"]
                tid = detection["track_id"]
                
                # Format the label to show speed for vehicles, but skip speed for people
                if detection["class_name"] != "person":
                    speed_str = f" | {int(self.tracked_vehicles.get(tid, {}).get('speed', 0))} km/h" if tid in self.tracked_vehicles else ""
                else:
                    speed_str = ""
                    
                label = f"ID:{tid} {detection['class_name']}{speed_str}"

                # Safely identify the specific violator comparing box coordinates
                is_violator = False
                if self.active_violations and target_ocr_box:
                    tx1, ty1, tx2, ty2 = target_ocr_box
                    if x1 == tx1 and y1 == ty1 and x2 == tx2 and y2 == ty2:
                        is_violator = True

                # Draw Red if Violator, Green if Normal
                if is_violator:
                    box_color = (0, 0, 255) # RED
                    if "helmet" in self.active_violations: 
                        label = "RIDER: NO HELMET"
                else:
                    box_color = (0, 255, 0) # GREEN

                cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
                cv2.rectangle(frame, (x1, y1 - 20), (x1 + len(label) * 8, y1), box_color, -1)
                cv2.putText(frame, label, (x1 + 2, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)

        # Draw the big red alert banner at the top left if there is an active violation
        if self.active_violations:
            cv2.rectangle(frame, (20, 40), (450, 75), (0, 0, 255), -1)
            cv2.putText(frame, f"VIOLATION: {' + '.join(self.active_violations).upper()} | {self.last_plate}", (35, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return result