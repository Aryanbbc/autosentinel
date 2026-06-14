import json
import math
import re
from collections import deque
from pathlib import Path

import cv2
import easyocr
import numpy as np
from ultralytics import YOLO


class ViolationDetector:
    """
    AutoSentinel detector:
    - Vehicle/person detection using YOLO
    - Optional license plate detector model
    - Optional helmet/no-helmet detector model
    - EasyOCR only on likely plate crops
    - Green boxes for normal detections, red boxes for violations
    """

    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent
        self.config_path = self.base_dir / "config.json"
        self.config = self._load_config()

        self.speed_limit_kmh = int(self.config.get("speed_limit_kmh", 60))
        self.fps = float(self.config.get("fps", 30.0))

        self.vehicle_conf = float(self.config.get("vehicle_confidence", 0.25))
        self.person_conf = float(self.config.get("person_confidence", 0.40))
        self.plate_conf = float(self.config.get("plate_confidence", 0.25))
        self.helmet_conf = float(self.config.get("helmet_confidence", 0.30))

        self.yolo_imgsz = int(self.config.get("yolo_imgsz", 960))
        self.plate_imgsz = int(self.config.get("plate_imgsz", 640))
        self.helmet_imgsz = int(self.config.get("helmet_imgsz", 640))

        self.ocr_every_n_frames = int(self.config.get("ocr_every_n_frames", 10))
        self.max_ocr_vehicles = int(self.config.get("max_ocr_vehicles", 3))
        self.plate_cache_ttl = int(self.config.get("plate_cache_ttl", 90))

        self.helmet_confirm_frames = int(self.config.get("helmet_confirm_frames", 8))
        self.violation_latch_total = int(self.config.get("violation_latch_frames", 25))

        self.line_start_y = int(self.config.get("line_start_y", 250))
        self.line_end_y = int(self.config.get("line_end_y", 450))
        self.zone_distance_meters = float(self.config.get("zone_distance_meters", 25.0))

        self.GREEN = (80, 255, 120)
        self.RED = (40, 40, 255)
        self.YELLOW = (0, 255, 255)
        self.WHITE = (255, 255, 255)
        self.BLACK = (0, 0, 0)

        self.yolo_model = self._load_vehicle_model()
        self.yolo_names = self.yolo_model.names

        self.plate_model = self._load_optional_model(
            config_key="plate_model_path",
            default_relative_path="models/license_plate_detector.pt",
            label="License Plate"
        )

        self.helmet_model = self._load_optional_model(
            config_key="helmet_model_path",
            default_relative_path="models/helmet_detector.pt",
            label="Helmet/No-Helmet"
        )

        print("Loading OCR Engine. First boot can take a few seconds...")
        self.reader = easyocr.Reader(["en"], gpu=bool(self.config.get("easyocr_gpu", False)))

        self.frame_count = 0
        self.tracked_vehicles = {}
        self.plate_cache = {}
        self.frame_buffer = deque(maxlen=30)

        self.helmet_frame_counter = 0
        self.violation_latch_frames = 0

        self.active_violations = []
        self.last_plate = "UNKNOWN"
        self.last_plate_box = None
        self.violation_box = None
        self.last_violation_label = ""

    def _load_config(self):
        default_config = {
            "speed_limit_kmh": 60,
            "fps": 30,
            "fines": {
                "helmet": 1000,
                "speed": 2000
            }
        }

        if not self.config_path.exists():
            return default_config

        try:
            with open(self.config_path, "r", encoding="utf-8") as file:
                loaded_config = json.load(file)
                default_config.update(loaded_config)
                return default_config
        except Exception as error:
            print(f"Config load failed, using defaults: {error}")
            return default_config

    def _load_vehicle_model(self):
        configured = self.config.get("vehicle_model_path")
        candidates = []

        if configured:
            configured_path = Path(configured)
            if not configured_path.is_absolute():
                configured_path = self.base_dir / configured_path
            candidates.append(str(configured_path))

        candidates.extend([
            str(self.base_dir / "models" / "yolov8s.pt"),
            str(self.base_dir / "yolov8s.pt"),
            "yolov8s.pt",
            str(self.base_dir / "models" / "yolov8n.pt"),
            str(self.base_dir / "yolov8n.pt"),
            "yolov8n.pt",
        ])

        last_error = None

        for candidate in candidates:
            try:
                print(f"Loading vehicle model: {candidate}")
                return YOLO(candidate)
            except Exception as error:
                last_error = error

        raise RuntimeError(f"Could not load any YOLO vehicle model. Last error: {last_error}")

    def _load_optional_model(self, config_key, default_relative_path, label):
        model_path = self.config.get(config_key, default_relative_path)
        model_path = Path(model_path)

        if not model_path.is_absolute():
            model_path = self.base_dir / model_path

        if not model_path.exists():
            print(f"{label} model not found at {model_path}. Fallback logic will be used.")
            return None

        try:
            print(f"Loading {label} model: {model_path}")
            return YOLO(str(model_path))
        except Exception as error:
            print(f"Failed to load {label} model: {error}")
            return None

    def _model_class_name(self, model, cls_id):
        names = getattr(model, "names", {})
        if isinstance(names, dict):
            return str(names.get(cls_id, cls_id)).lower()
        if isinstance(names, list) and 0 <= cls_id < len(names):
            return str(names[cls_id]).lower()
        return str(cls_id).lower()

    def _get_yolo_detections(self, yolo_results):
        detections = []

        if yolo_results is None or yolo_results.boxes is None:
            return detections

        for box in yolo_results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)

            track_id = -1
            if box.id is not None:
                try:
                    track_id = int(box.id[0])
                except Exception:
                    track_id = -1

            class_name = self._model_class_name(self.yolo_model, cls_id)

            detections.append({
                "class_id": cls_id,
                "class_name": class_name,
                "confidence": conf,
                "box": [x1, y1, x2, y2],
                "track_id": track_id
            })

        return detections

    def _is_vehicle(self, detection):
        return detection["class_name"] in {"car", "truck", "bus", "motorcycle"}

    def _is_drawable_object(self, detection):
        return detection["class_name"] in {"person", "car", "truck", "bus", "motorcycle"}

    def _area(self, box):
        x1, y1, x2, y2 = box
        return max(0, x2 - x1) * max(0, y2 - y1)

    def _iou(self, box_a, box_b):
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b

        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)

        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        union = self._area(box_a) + self._area(box_b) - inter

        if union <= 0:
            return 0.0

        return inter / union

    def _overlap_area(self, box_a, box_b):
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b

        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)

        if ix1 >= ix2 or iy1 >= iy2:
            return 0

        return (ix2 - ix1) * (iy2 - iy1)

    def _clamp_box(self, box, width, height):
        x1, y1, x2, y2 = box
        return [
            max(0, min(width - 1, int(x1))),
            max(0, min(height - 1, int(y1))),
            max(0, min(width - 1, int(x2))),
            max(0, min(height - 1, int(y2))),
        ]

    def _track_key(self, detection):
        if detection.get("track_id", -1) != -1:
            return f"id_{detection['track_id']}"

        x1, y1, x2, y2 = detection["box"]
        return f"box_{x1}_{y1}_{x2}_{y2}"

    def _find_related_rider_box(self, no_helmet_box, detections):
        persons = [
            d for d in detections
            if d["class_name"] == "person" and d["confidence"] >= self.person_conf
        ]

        motorcycles = [
            d for d in detections
            if d["class_name"] == "motorcycle" and d["confidence"] >= self.vehicle_conf
        ]

        cx = (no_helmet_box[0] + no_helmet_box[2]) // 2
        cy = (no_helmet_box[1] + no_helmet_box[3]) // 2

        best_person = None
        best_score = 0

        for person in persons:
            px1, py1, px2, py2 = person["box"]
            inside_person = px1 <= cx <= px2 and py1 <= cy <= py2
            overlap = self._overlap_area(no_helmet_box, person["box"])

            score = overlap
            if inside_person:
                score += self._area(no_helmet_box)

            if score > best_score:
                best_score = score
                best_person = person

        if best_person is None:
            return no_helmet_box

        final_box = best_person["box"]

        for moto in motorcycles:
            overlap = self._overlap_area(best_person["box"], moto["box"])
            if overlap > 0:
                x1 = min(final_box[0], moto["box"][0])
                y1 = min(final_box[1], moto["box"][1])
                x2 = max(final_box[2], moto["box"][2])
                y2 = max(final_box[3], moto["box"][3])
                final_box = [x1, y1, x2, y2]
                break

        return final_box

    def _check_custom_helmet_model(self, frame, detections):
        if self.helmet_model is None:
            return False, None

        try:
            results = self.helmet_model(
                frame,
                imgsz=self.helmet_imgsz,
                conf=self.helmet_conf,
                verbose=False
            )[0]
        except Exception as error:
            print(f"Helmet model inference failed: {error}")
            return False, None

        if results.boxes is None:
            return False, None

        best_no_helmet_box = None
        best_conf = 0.0

        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            class_name = self._model_class_name(self.helmet_model, cls_id)

            normalized_name = (
                class_name
                .replace(" ", "")
                .replace("-", "")
                .replace("_", "")
                .lower()
            )

            is_no_helmet = (
                "nohelmet" in normalized_name
                or "withouthelmet" in normalized_name
                or normalized_name in {"head", "barehead"}
            )

            if not is_no_helmet:
                continue

            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)

            if conf > best_conf:
                best_conf = conf
                best_no_helmet_box = [x1, y1, x2, y2]

        if best_no_helmet_box is None:
            return False, None

        return True, self._find_related_rider_box(best_no_helmet_box, detections)

    def _check_heuristic_no_helmet(self, frame, detections):
        persons = [
            d for d in detections
            if d["class_name"] == "person" and d["confidence"] >= self.person_conf
        ]

        motorcycles = [
            d for d in detections
            if d["class_name"] == "motorcycle" and d["confidence"] >= self.vehicle_conf
        ]

        if not persons or not motorcycles:
            return False, None

        frame_height, frame_width = frame.shape[:2]

        for person in persons:
            px1, py1, px2, py2 = person["box"]
            person_box = [px1, py1, px2, py2]
            person_area = max(1, self._area(person_box))

            is_riding = False

            for moto in motorcycles:
                overlap = self._overlap_area(person_box, moto["box"])
                if overlap / person_area > 0.12:
                    is_riding = True
                    break

            if not is_riding:
                continue

            px1, py1, px2, py2 = self._clamp_box(person_box, frame_width, frame_height)
            person_height = py2 - py1

            if person_height <= 0:
                continue

            head_y2 = py1 + int(person_height * 0.28)
            head_crop = frame[py1:head_y2, px1:px2]

            if head_crop.size == 0:
                continue

            gray = cv2.cvtColor(head_crop, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)

            edges = cv2.Canny(gray, 40, 120)
            edge_density = np.count_nonzero(edges) / max(1, edges.size)

            mean_intensity = float(np.mean(gray))
            std_intensity = float(np.std(gray))

            _, threshold = cv2.threshold(
                gray,
                0,
                255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )

            contours, _ = cv2.findContours(
                threshold,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            helmet_shape_found = False

            for contour in contours:
                area = cv2.contourArea(contour)
                perimeter = cv2.arcLength(contour, True)

                if area < 50 or perimeter <= 0:
                    continue

                circularity = 4 * math.pi * area / (perimeter ** 2)

                if 0.35 <= circularity <= 1.25:
                    helmet_shape_found = True
                    break

            helmet_texture = (
                edge_density > 0.060
                or mean_intensity < 70
                or mean_intensity > 185
                or std_intensity > 55
            )

            helmet_likely = helmet_shape_found and helmet_texture

            if not helmet_likely:
                return True, person_box

        return False, None

    def check_frame_for_no_helmet(self, frame, detections):
        custom_detected, custom_box = self._check_custom_helmet_model(frame, detections)

        if custom_detected:
            return True, custom_box

        return self._check_heuristic_no_helmet(frame, detections)

    def _crossed_line(self, previous_y, current_y, line_y):
        if previous_y is None:
            return False

        return (
            previous_y < line_y <= current_y
            or previous_y > line_y >= current_y
        )

    def check_for_speeding(self, detections):
        speeding_vehicles = []

        for detection in detections:
            if not self._is_vehicle(detection):
                continue

            if detection["track_id"] == -1:
                continue

            x1, y1, x2, y2 = detection["box"]
            center_y = (y1 + y2) // 2
            track_id = detection["track_id"]

            if track_id not in self.tracked_vehicles:
                self.tracked_vehicles[track_id] = {
                    "previous_y": None,
                    "start_frame": None,
                    "speed": 0.0,
                    "ticketed": False
                }

            memory = self.tracked_vehicles[track_id]
            previous_y = memory.get("previous_y")

            if self._crossed_line(previous_y, center_y, self.line_start_y):
                memory["start_frame"] = self.frame_count
                memory["ticketed"] = False

            if self._crossed_line(previous_y, center_y, self.line_end_y):
                start_frame = memory.get("start_frame")

                if start_frame is not None and not memory.get("ticketed", False):
                    frames_passed = max(1, self.frame_count - start_frame)
                    time_seconds = frames_passed / max(1.0, self.fps)
                    speed_ms = self.zone_distance_meters / time_seconds
                    speed_kmh = speed_ms * 3.6

                    memory["speed"] = speed_kmh
                    memory["ticketed"] = True

                    if speed_kmh > self.speed_limit_kmh:
                        speeding_vehicles.append((detection, speed_kmh))

            memory["previous_y"] = center_y

        return speeding_vehicles

    def _plate_image_variants(self, plate_crop):
        if plate_crop is None or plate_crop.size == 0:
            return []

        variants = []

        try:
            upscaled = cv2.resize(
                plate_crop,
                None,
                fx=3,
                fy=3,
                interpolation=cv2.INTER_CUBIC
            )
        except Exception:
            return []

        variants.append(upscaled)

        try:
            gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
            gray = cv2.bilateralFilter(gray, 11, 17, 17)

            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            variants.append(enhanced)

            threshold = cv2.adaptiveThreshold(
                enhanced,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                31,
                2
            )
            variants.append(threshold)
        except Exception:
            pass

        return variants

    def _clean_plate_text(self, text):
        clean = re.sub(r"[^A-Z0-9]", "", text.upper())

        bad_words = [
            "GOODS", "CARRIER", "INDIA", "STOP", "HORN", "MAMTA",
            "TAX", "PERMIT", "PETROL", "DIESEL", "GOVT", "POLICE",
            "BHARAT", "AGENCY", "ROAD", "TRANSPORT", "LOGISTICS"
        ]

        for word in bad_words:
            clean = clean.replace(word, "")

        return clean

    def _extract_indian_plate_candidates(self, clean_text):
        candidates = []

        if not clean_text:
            return candidates

        direct_matches = re.findall(
            r"[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}",
            clean_text
        )
        candidates.extend(direct_matches)

        fixed = (
            clean_text
            .replace("O", "0")
            .replace("I", "1")
            .replace("Q", "0")
        )

        fixed_matches = re.findall(
            r"[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}",
            fixed
        )
        candidates.extend(fixed_matches)

        unique = []
        seen = set()

        for candidate in candidates:
            if 7 <= len(candidate) <= 11 and candidate not in seen:
                unique.append(candidate[:10])
                seen.add(candidate)

        return unique

    def _scan_for_plate(self, image_crop):
        if image_crop is None or image_crop.size == 0:
            return None

        best_plate = None
        best_score = 0.0

        variants = self._plate_image_variants(image_crop)

        for variant in variants:
            try:
                ocr_results = self.reader.readtext(
                    variant,
                    allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                    detail=1,
                    paragraph=False,
                    contrast_ths=0.05,
                    adjust_contrast=0.7,
                    width_ths=0.7
                )
            except Exception:
                continue

            combined_raw = "".join([text for (_bbox, text, prob) in ocr_results if prob >= 0.10])
            combined_clean = self._clean_plate_text(combined_raw)

            for candidate in self._extract_indian_plate_candidates(combined_clean):
                score = 0.60
                if score > best_score:
                    best_plate = candidate
                    best_score = score

            for _bbox, text, prob in ocr_results:
                clean = self._clean_plate_text(text)
                candidates = self._extract_indian_plate_candidates(clean)

                for candidate in candidates:
                    score = float(prob)
                    if score > best_score:
                        best_plate = candidate
                        best_score = score

        return best_plate

    def _choose_target_vehicle(self, detections, target_box=None):
        vehicles = [
            d for d in detections
            if self._is_vehicle(d) and d["confidence"] >= self.vehicle_conf
        ]

        if not vehicles:
            return None

        if target_box is not None:
            best_vehicle = None
            best_score = 0

            for vehicle in vehicles:
                overlap = self._overlap_area(vehicle["box"], target_box)
                score = overlap

                if score > best_score:
                    best_score = score
                    best_vehicle = vehicle

            if best_vehicle is not None:
                return best_vehicle

        vehicles.sort(key=lambda d: self._area(d["box"]), reverse=True)
        return vehicles[0]

    def _extract_plate_from_vehicle(self, frame, vehicle):
        h, w = frame.shape[:2]
        vx1, vy1, vx2, vy2 = self._clamp_box(vehicle["box"], w, h)

        if vx2 <= vx1 or vy2 <= vy1:
            return "UNKNOWN", None

        vehicle_crop = frame[vy1:vy2, vx1:vx2]

        if vehicle_crop.size == 0:
            return "UNKNOWN", None

        if self.plate_model is not None:
            try:
                plate_results = self.plate_model(
                    vehicle_crop,
                    imgsz=self.plate_imgsz,
                    conf=self.plate_conf,
                    verbose=False
                )[0]

                best_candidate = None
                best_conf = 0.0

                if plate_results.boxes is not None:
                    for box in plate_results.boxes:
                        conf = float(box.conf[0])
                        px1, py1, px2, py2 = box.xyxy[0].cpu().numpy().astype(int)

                        crop_h, crop_w = vehicle_crop.shape[:2]
                        px1, py1, px2, py2 = self._clamp_box([px1, py1, px2, py2], crop_w, crop_h)

                        if px2 <= px1 or py2 <= py1:
                            continue

                        plate_crop = vehicle_crop[py1:py2, px1:px2]
                        plate_text = self._scan_for_plate(plate_crop)

                        if plate_text and conf > best_conf:
                            abs_box = [vx1 + px1, vy1 + py1, vx1 + px2, vy1 + py2]
                            best_candidate = (plate_text, abs_box)
                            best_conf = conf

                if best_candidate is not None:
                    return best_candidate

            except Exception as error:
                print(f"Plate model inference failed: {error}")

        vh, vw = vehicle_crop.shape[:2]
        candidate_regions = []
        class_name = vehicle.get("class_name", "")

        if class_name == "motorcycle":
            candidate_regions.extend([
                ("moto_lower", [int(vw * 0.15), int(vh * 0.45), int(vw * 0.85), vh]),
                ("moto_center", [int(vw * 0.20), int(vh * 0.30), int(vw * 0.80), int(vh * 0.80)]),
                ("moto_full", [0, 0, vw, vh]),
            ])
        else:
            candidate_regions.extend([
                ("vehicle_lower_center", [int(vw * 0.12), int(vh * 0.45), int(vw * 0.88), vh]),
                ("vehicle_lower_full", [0, int(vh * 0.40), vw, vh]),
                ("vehicle_middle", [int(vw * 0.10), int(vh * 0.25), int(vw * 0.90), int(vh * 0.75)]),
                ("vehicle_full", [0, 0, vw, vh]),
            ])

        for _name, region in candidate_regions:
            rx1, ry1, rx2, ry2 = self._clamp_box(region, vw, vh)

            if rx2 <= rx1 or ry2 <= ry1:
                continue

            crop = vehicle_crop[ry1:ry2, rx1:rx2]

            if crop.size == 0:
                continue

            plate_text = self._scan_for_plate(crop)

            if plate_text:
                abs_box = [vx1 + rx1, vy1 + ry1, vx1 + rx2, vy1 + ry2]
                return plate_text, abs_box

        return "UNKNOWN", None

    def extract_license_plate(self, frame, detections, target_box=None):
        target_vehicle = self._choose_target_vehicle(detections, target_box)

        if target_vehicle is None:
            self.last_plate_box = None
            return "UNKNOWN"

        plate_text, plate_box = self._extract_plate_from_vehicle(frame, target_vehicle)
        self.last_plate_box = plate_box

        return plate_text if plate_text else "UNKNOWN"

    def _update_plate_cache(self, frame, detections):
        expired_keys = []

        for key, value in self.plate_cache.items():
            value["ttl"] -= 1
            if value["ttl"] <= 0:
                expired_keys.append(key)

        for key in expired_keys:
            self.plate_cache.pop(key, None)

        if self.ocr_every_n_frames <= 0:
            return

        if self.frame_count % self.ocr_every_n_frames != 0:
            return

        vehicles = [
            d for d in detections
            if self._is_vehicle(d) and d["confidence"] >= self.vehicle_conf
        ]

        vehicles.sort(key=lambda d: self._area(d["box"]), reverse=True)
        vehicles = vehicles[:self.max_ocr_vehicles]

        for vehicle in vehicles:
            key = self._track_key(vehicle)

            cached = self.plate_cache.get(key)
            if cached and cached.get("plate") != "UNKNOWN":
                continue

            plate_text, plate_box = self._extract_plate_from_vehicle(frame, vehicle)

            if plate_text and plate_text != "UNKNOWN":
                self.plate_cache[key] = {
                    "plate": plate_text,
                    "box": plate_box,
                    "ttl": self.plate_cache_ttl
                }

    def _draw_label(self, frame, text, x, y, color, font_scale=0.45):
        if not text:
            return

        h, w = frame.shape[:2]
        x = max(0, min(w - 1, int(x)))
        y = max(18, min(h - 1, int(y)))

        text_size, _ = cv2.getTextSize(
            text,
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            1
        )

        text_w, text_h = text_size
        rect_x2 = min(w - 1, x + text_w + 10)
        rect_y1 = max(0, y - text_h - 8)

        cv2.rectangle(frame, (x, rect_y1), (rect_x2, y + 4), color, -1)
        cv2.putText(
            frame,
            text,
            (x + 5, y - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            self.BLACK,
            1,
            cv2.LINE_AA
        )

    def _draw_plate_text(self, frame, plate_text, vehicle_box, plate_box=None):
        if not plate_text or plate_text == "UNKNOWN":
            return

        x1, y1, x2, y2 = vehicle_box
        h, w = frame.shape[:2]

        if plate_box is not None:
            px1, py1, px2, py2 = self._clamp_box(plate_box, w, h)
            cv2.rectangle(frame, (px1, py1), (px2, py2), self.GREEN, 2)

        label_y = min(h - 8, y2 + 28)

        cv2.putText(
            frame,
            plate_text,
            (x1, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            self.GREEN,
            2,
            cv2.LINE_AA
        )

    def _draw_speed_zone(self, frame):
        h, w = frame.shape[:2]

        if 0 <= self.line_start_y < h:
            cv2.line(frame, (0, self.line_start_y), (w, self.line_start_y), self.YELLOW, 1)
            cv2.putText(
                frame,
                "SPEED ZONE START",
                (10, max(15, self.line_start_y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                self.YELLOW,
                1,
                cv2.LINE_AA
            )

        if 0 <= self.line_end_y < h:
            cv2.line(frame, (0, self.line_end_y), (w, self.line_end_y), self.YELLOW, 2)
            cv2.putText(
                frame,
                "SPEED ZONE END",
                (10, max(15, self.line_end_y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                self.YELLOW,
                1,
                cv2.LINE_AA
            )

    def _draw_detections(self, frame, detections):
        for detection in detections:
            if not self._is_drawable_object(detection):
                continue

            conf_needed = self.person_conf if detection["class_name"] == "person" else self.vehicle_conf
            if detection["confidence"] < conf_needed:
                continue

            x1, y1, x2, y2 = detection["box"]
            class_name = detection["class_name"]
            tid = detection["track_id"]

            is_violator = False

            if self.active_violations and self.violation_box is not None:
                if self._iou(detection["box"], self.violation_box) > 0.20:
                    is_violator = True

            box_color = self.RED if is_violator else self.GREEN

            if is_violator:
                if "helmet" in self.active_violations:
                    label = "NO HELMET"
                elif "speed" in self.active_violations:
                    label = "SPEEDING"
                else:
                    label = "VIOLATION"
            else:
                label = class_name.upper()

            if tid != -1:
                label = f"ID:{tid} {label}"

            if class_name != "person" and tid in self.tracked_vehicles:
                speed = int(self.tracked_vehicles[tid].get("speed", 0))
                if speed > 0:
                    label += f" | {speed} km/h"

            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            self._draw_label(frame, label, x1, y1, box_color, font_scale=0.45)

            if self._is_vehicle(detection):
                key = self._track_key(detection)
                cached_plate = self.plate_cache.get(key)

                if cached_plate:
                    self._draw_plate_text(
                        frame,
                        cached_plate.get("plate"),
                        detection["box"],
                        cached_plate.get("box")
                    )

    def _draw_alert_banner(self, frame):
        if not self.active_violations:
            return

        h, w = frame.shape[:2]

        banner_x1, banner_y1 = 20, 35
        banner_x2, banner_y2 = min(w - 20, 560), 82

        cv2.rectangle(frame, (banner_x1, banner_y1), (banner_x2, banner_y2), self.RED, -1)

        text = f"VIOLATION: {' + '.join(self.active_violations).upper()} | {self.last_plate}"

        cv2.putText(
            frame,
            text,
            (banner_x1 + 15, banner_y1 + 31),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            self.WHITE,
            2,
            cv2.LINE_AA
        )

    def process_frame(self, frame):
        self.frame_count += 1

        result = {
            "violations": [],
            "confidence": {},
            "boxes": [],
            "new_alert": False,
            "plate": "UNKNOWN",
            "fine_total": 0
        }

        if frame is None:
            return result

        self.frame_buffer.append(frame.copy())

        try:
            yolo_result = self.yolo_model.track(
                frame,
                persist=True,
                verbose=False,
                imgsz=self.yolo_imgsz,
                conf=self.vehicle_conf,
                iou=0.45,
                classes=[0, 2, 3, 5, 7]
            )[0]
        except Exception as error:
            print(f"YOLO inference failed: {error}")
            return result

        detections = self._get_yolo_detections(yolo_result)
        result["boxes"] = [d["box"] for d in detections]
        result["confidence"] = {
            "detections": len(detections),
            "vehicles": len([d for d in detections if self._is_vehicle(d)]),
            "persons": len([d for d in detections if d["class_name"] == "person"])
        }

        self._update_plate_cache(frame, detections)

        current_frame_violations = []
        target_ocr_box = None

        no_helmet_detected, helmet_violator_box = self.check_frame_for_no_helmet(frame, detections)

        if no_helmet_detected:
            self.helmet_frame_counter += 1

            if self.helmet_frame_counter >= self.helmet_confirm_frames:
                current_frame_violations.append("helmet")
                target_ocr_box = helmet_violator_box
                self.violation_box = helmet_violator_box
                self.last_violation_label = "NO HELMET"
        else:
            self.helmet_frame_counter = max(0, self.helmet_frame_counter - 1)

        speeders = self.check_for_speeding(detections)

        for speeder_dict, speed_kmh in speeders:
            current_frame_violations.append("speed")
            target_ocr_box = speeder_dict["box"]
            self.violation_box = speeder_dict["box"]
            self.last_violation_label = f"SPEEDING {int(speed_kmh)} km/h"

            x1, y1, _x2, _y2 = speeder_dict["box"]
            cv2.putText(
                frame,
                f"SPEEDING: {int(speed_kmh)} km/h",
                (x1, max(20, y1 - 35)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                self.RED,
                2,
                cv2.LINE_AA
            )

        if current_frame_violations:
            self.active_violations = current_frame_violations

            if self.violation_latch_frames == 0:
                result["new_alert"] = True

                self.last_plate = self.extract_license_plate(
                    frame,
                    detections,
                    target_ocr_box
                )

                target_vehicle = self._choose_target_vehicle(detections, target_ocr_box)
                if target_vehicle is not None and self.last_plate != "UNKNOWN":
                    key = self._track_key(target_vehicle)
                    self.plate_cache[key] = {
                        "plate": self.last_plate,
                        "box": self.last_plate_box,
                        "ttl": self.plate_cache_ttl
                    }

                print(
                    f"🚨 AUTOSENTINEL: "
                    f"{', '.join(self.active_violations).upper()} -> Plate: {self.last_plate}"
                )

            self.violation_latch_frames = self.violation_latch_total

        else:
            if self.violation_latch_frames > 0:
                self.violation_latch_frames -= 1
            else:
                self.active_violations = []
                self.violation_box = None
                self.last_violation_label = ""

        result["plate"] = self.last_plate

        if self.active_violations:
            result["violations"] = self.active_violations

        fines = self.config.get("fines", {})
        fine_total = 0

        for violation in result["violations"]:
            fine_total += int(fines.get(violation, 0))

        result["fine_total"] = fine_total

        self._draw_speed_zone(frame)
        self._draw_detections(frame, detections)

        if self.last_plate_box is not None and self.last_plate != "UNKNOWN":
            self._draw_plate_text(
                frame,
                self.last_plate,
                self.violation_box or self.last_plate_box,
                self.last_plate_box
            )

        self._draw_alert_banner(frame)

        return result