import os
import json
import random
import asyncio
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import uvicorn
from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    from .challan import generate_challan
    from .database import (
        get_all_violations,
        get_stats,
        get_violation_by_id,
        init_db,
        insert_dispute,
        insert_vehicle,
        insert_violation,
        seed_mock_data,
    )
except ImportError:
    from challan import generate_challan
    from database import (
        get_all_violations,
        get_stats,
        get_violation_by_id,
        init_db,
        insert_dispute,
        insert_vehicle,
        insert_violation,
        seed_mock_data,
    )


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

CONFIG_PATH = BASE_DIR / "config.json"
CHALLAN_DIR = PROJECT_ROOT / "challans"
CHALLAN_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AutoSentinel Backend", version="1.0.0")


# ---------------- CORS CONFIG ----------------

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://autosentinel-tnvc.vercel.app")

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    FRONTEND_URL,
    "https://autosentinel-tnvc.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(set(allowed_origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- MODELS ----------------

class DisputeRequest(BaseModel):
    reason: str


# ---------------- CONFIG ----------------

def load_config():
    default_config = {
        "speed_limit_kmh": 60,
        "fines": {
            "helmet": 1000,
            "speed": 2000,
            "seatbelt": 1000,
            "phone": 1500,
            "wrong_way": 2000,
            "drowsiness": 1000,
        },
        "camera_unit_id": "CAM-DL-001",
        "mock_gps": "28.6139N, 77.2090E",
    }

    if not CONFIG_PATH.exists():
        return default_config

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            loaded = json.load(file)

        default_config.update(loaded)

        if "fines" in loaded:
            default_config["fines"].update(loaded.get("fines", {}))

        return default_config

    except Exception as error:
        print(f"⚠️ Config load failed. Using default config. Error: {error}")
        return default_config


# ---------------- VIDEO PATH ----------------

def get_video_path():
    env_path = os.getenv("TRAFFIC_VIDEO_PATH")

    candidates = []

    if env_path:
        candidates.append(Path(env_path))

    candidates.extend([
        BASE_DIR / "traffic.mp4",
        BASE_DIR / "demo_footage" / "traffic.mp4",
        PROJECT_ROOT / "traffic.mp4",
        PROJECT_ROOT / "demo_footage" / "traffic.mp4",
    ])

    for path in candidates:
        if path.exists():
            return path

    return None


# ---------------- PLACEHOLDER FRAME ----------------

def create_placeholder_frame(message="traffic.mp4 not found"):
    frame = cv2.UMat(720, 1280, cv2.CV_8UC3).get()
    frame[:] = (5, 8, 12)

    cv2.putText(
        frame,
        "AUTOSENTINEL LIVE FEED",
        (330, 300),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.4,
        (80, 255, 120),
        3,
        cv2.LINE_AA,
    )

    cv2.putText(
        frame,
        message,
        (360, 370),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (80, 80, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.putText(
        frame,
        "Add traffic.mp4 inside backend/ or set TRAFFIC_VIDEO_PATH",
        (270, 430),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (180, 180, 180),
        2,
        cv2.LINE_AA,
    )

    return frame


def encode_frame_to_base64(frame):
    success, buffer = cv2.imencode(".jpg", frame)

    if not success:
        return None

    return base64.b64encode(buffer).decode("utf-8")


# ---------------- CHALLAN ----------------

def ensure_challan_exists(case_id):
    pdf_path = CHALLAN_DIR / f"challan_{case_id}.pdf"

    if pdf_path.exists():
        return str(pdf_path)

    violation = get_violation_by_id(case_id)

    if violation is None:
        return None

    violation_data = {
        "case_id": violation["id"],
        "plate": violation["plate"],
        "owner_name": violation.get("owner_name") or "Unknown",
        "contact": violation.get("contact") or "Not Available",
        "vehicle_type": violation.get("vehicle_type") or "Unknown",
        "violation_type": violation["violation_type"],
        "timestamp": violation["timestamp"],
        "location": violation["location"],
        "fine_amount": violation["fine_amount"],
        "speed": violation.get("speed") or 0,
        "evidence_paths": violation.get("evidence_paths") or "",
    }

    return generate_challan(
        violation_data=violation_data,
        evidence_paths=violation.get("evidence_paths") or "",
    )


# ---------------- MOCK DATA HELPERS ----------------

def create_mock_vehicle_if_missing(plate):
    mock_owners = [
        ("Aryan Mehta", "+919870001101", "Car"),
        ("Riya Sharma", "+919870001102", "Scooter"),
        ("Kabir Singh", "+919870001103", "Bike"),
        ("Ananya Gupta", "+919870001104", "Car"),
        ("Rahul Verma", "+919870001105", "Bike"),
        ("Neha Malhotra", "+919870001106", "Car"),
    ]

    owner_name, contact, vehicle_type = random.choice(mock_owners)

    try:
        insert_vehicle(plate, owner_name, contact, vehicle_type)
    except Exception as error:
        print(f"⚠️ Vehicle insert skipped/failed: {error}")


def create_live_fine(detected_plate, violations):
    config = load_config()

    if detected_plate and detected_plate != "UNKNOWN":
        plate = detected_plate
    else:
        plate = random.choice([
            "DL8CAF4321",
            "MH12AB1234",
            "KA05MN9087",
            "UP16CD7788",
            "HR26DK8337",
        ])

    if not violations:
        violations = ["helmet"]

    create_mock_vehicle_if_missing(plate)

    fines_dict = config.get("fines", {})
    fine_amount = sum(int(fines_dict.get(v, 1000)) for v in violations)
    primary_violation = violations[0]

    timestamp = datetime.now().isoformat(timespec="seconds")

    case_id = insert_violation(
        plate=plate,
        violation_type=primary_violation,
        timestamp=timestamp,
        location=config.get("mock_gps", "28.6139N, 77.2090E"),
        fine_amount=fine_amount,
        speed=0,
        evidence_paths=[],
        status="unpaid",
    )

    return {
        "case_id": case_id,
        "plate": plate,
        "violation_type": primary_violation,
        "violations": violations,
        "timestamp": timestamp,
        "fine_total": fine_amount,
        "camera_unit_id": config.get("camera_unit_id", "CAM-DL-001"),
        "location": config.get("mock_gps", "28.6139N, 77.2090E"),
    }


# ---------------- STARTUP ----------------

@app.on_event("startup")
def startup_event():
    init_db()
    seed_mock_data()
    print("✅ AutoSentinel backend is running.")


# ---------------- REST ROUTES ----------------

@app.get("/")
def root():
    return {
        "app": "AutoSentinel",
        "status": "running",
        "docs": "/docs",
        "live_feed": "/ws/live-feed",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "backend": "running",
        "time": datetime.now().isoformat(timespec="seconds"),
    }


@app.get("/violations")
def violations(
    date: Optional[str] = Query(default=None),
    type: Optional[str] = Query(default=None),
    plate: Optional[str] = Query(default=None),
):
    return get_all_violations(date=date, violation_type=type, plate=plate)


@app.get("/stats")
def stats():
    return get_stats()


@app.get("/simulate-violation")
def simulate_violation():
    alert = create_live_fine(
        detected_plate=random.choice([
            "DL8CAF4321",
            "MH12AB1234",
            "KA05MN9087",
            "UP16CD7788",
            "HR26DK8337",
        ]),
        violations=[random.choice(["helmet", "speed", "phone", "seatbelt"])],
    )

    return {
        "success": True,
        **alert,
    }


@app.post("/dispute/{case_id}")
def dispute(case_id: str, payload: DisputeRequest = Body(...)):
    reason = payload.reason.strip()

    if not reason:
        raise HTTPException(status_code=400, detail="Dispute reason cannot be empty")

    dispute_id = insert_dispute(violation_id=case_id, reason=reason)

    if dispute_id is None:
        raise HTTPException(status_code=404, detail="Violation case not found")

    return {
        "success": True,
        "case_id": case_id,
        "dispute_id": dispute_id,
        "status": "pending",
    }


@app.get("/challan/{case_id}")
def challan(case_id: str):
    pdf_path = ensure_challan_exists(case_id)

    if pdf_path is None:
        raise HTTPException(status_code=404, detail="Violation case not found")

    path = Path(pdf_path)

    if not path.exists():
        raise HTTPException(status_code=500, detail="Challan could not be generated")

    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=f"challan_{case_id}.pdf",
    )


# ---------------- WEBSOCKET CORE ----------------

async def websocket_live_feed(websocket: WebSocket):
    await websocket.accept()
    print("✅ WebSocket client connected")

    video_path = get_video_path()

    if video_path:
        print(f"🎥 Using video: {video_path}")
        camera = cv2.VideoCapture(str(video_path))
    else:
        print("⚠️ traffic.mp4 not found. Sending placeholder frames.")
        camera = None

    detector = None

    try:
        from detector import ViolationDetector
        detector = ViolationDetector()
        print("✅ Detector loaded")
    except Exception as error:
        print(f"⚠️ Detector failed to load. Streaming without AI. Error: {error}")

    try:
        while True:
            if camera is not None:
                success, frame = camera.read()

                if not success:
                    camera.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
            else:
                frame = create_placeholder_frame()

            alert_data = None
            ai_results = {
                "violations": [],
                "plate": "UNKNOWN",
                "new_alert": False,
                "fine_total": 0,
            }

            if detector is not None:
                try:
                    ai_results = detector.process_frame(frame)

                    if ai_results.get("new_alert"):
                        scanned_plate = ai_results.get("plate", "UNKNOWN")
                        active_violations = ai_results.get("violations", ["helmet"])

                        alert_data = create_live_fine(
                            detected_plate=scanned_plate,
                            violations=active_violations,
                        )

                except Exception as ai_error:
                    print(f"❌ AI ERROR: {ai_error}")

            frame_text = encode_frame_to_base64(frame)

            if frame_text is None:
                continue

            payload = {
                "frame": frame_text,
                "image": frame_text,
                "alert": alert_data,
                "new_alert": bool(alert_data),
                "violations": ai_results.get("violations", []),
                "plate": ai_results.get("plate", "UNKNOWN"),
                "fine_total": ai_results.get("fine_total", 0),
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            }

            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1 / 15)

    except WebSocketDisconnect:
        print("🔌 Client disconnected")

    except Exception as error:
        print(f"⚠️ WebSocket error: {error}")

    finally:
        if camera is not None:
            camera.release()

        print("🧹 WebSocket cleaned up")


# Main production route
@app.websocket("/ws/live-feed")
async def live_feed_ws(websocket: WebSocket):
    await websocket_live_feed(websocket)


# Old route also supported
@app.websocket("/ws/live-feed")
async def live_feed(websocket: WebSocket):
    await websocket_live_feed(websocket)


# ---------------- RUN LOCAL ----------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)