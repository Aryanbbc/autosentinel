import json
import random
import asyncio
import cv2     
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    from .challan import generate_challan
    from .database import (
        get_all_violations, get_stats, get_violation_by_id, init_db,
        insert_dispute, insert_vehicle, insert_violation, seed_mock_data
    )
except ImportError:
    from challan import generate_challan
    from database import (
        get_all_violations, get_stats, get_violation_by_id, init_db,
        insert_dispute, insert_vehicle, insert_violation, seed_mock_data
    )

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
CONFIG_PATH = BASE_DIR / "config.json"
CHALLAN_DIR = PROJECT_ROOT / "challans"

CHALLAN_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AutoSentinel Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://127.0.0.1:5173",
        "https://autosentinel-tnvc.vercel.app"  # Added your live Vercel URL
    ],
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

class DisputeRequest(BaseModel):
    reason: str

def load_config():
    default_config = {
        "speed_limit_kmh": 60, "fines": {"helmet": 1000, "speed": 2000},
        "camera_unit_id": "CAM-DL-001", "mock_gps": "28.6139N, 77.2090E"
    }
    if not CONFIG_PATH.exists(): return default_config
    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        loaded = json.load(file)
    default_config.update(loaded)
    default_config["fines"].update(loaded.get("fines", {}))
    return default_config

def ensure_challan_exists(case_id):
    pdf_path = CHALLAN_DIR / f"challan_{case_id}.pdf"
    if pdf_path.exists(): return str(pdf_path)
    violation = get_violation_by_id(case_id)
    if violation is None: return None
    violation_data = {
        "case_id": violation["id"], "plate": violation["plate"],
        "owner_name": violation.get("owner_name") or "Unknown",
        "contact": violation.get("contact") or "Not Available",
        "vehicle_type": violation.get("vehicle_type") or "Unknown",
        "violation_type": violation["violation_type"],
        "timestamp": violation["timestamp"], "location": violation["location"],
        "fine_amount": violation["fine_amount"], "speed": violation.get("speed") or 0,
        "evidence_paths": violation.get("evidence_paths") or ""
    }
    return generate_challan(violation_data=violation_data, evidence_paths=violation.get("evidence_paths") or "")

def create_mock_vehicle_if_missing(plate):
    mock_owners = [
        ("Aryan Mehta", "+919870001101", "Car"), ("Riya Sharma", "+919870001102", "Scooter"),
        ("Kabir Singh", "+919870001103", "Bike"), ("Ananya Gupta", "+919870001104", "Car")
    ]
    owner_name, contact, vehicle_type = random.choice(mock_owners)
    insert_vehicle(plate, owner_name, contact, vehicle_type)

# === UPGRADED OMNI-CAM FINE GENERATOR ===
def create_live_fine(detected_plate, violations):
    config = load_config()
    
    if detected_plate and detected_plate != "UNKNOWN":
        plate = detected_plate
    else:
        plate = random.choice(["DL8CAF4321", "MH12AB1234", "KA05MN9087"])
        
    create_mock_vehicle_if_missing(plate)

    # Dynamic Math: Add up the fines for ALL concurrent violations!
    fines_dict = config.get("fines", {"helmet": 1000, "speed": 2000})
    fine_amount = sum(int(fines_dict.get(v, 1000)) for v in violations)
    primary_violation = violations[0] if violations else "helmet"

    timestamp = datetime.now().isoformat(timespec="seconds")
    
    case_id = insert_violation(
        plate=plate, violation_type=primary_violation, timestamp=timestamp,
        location=config.get("mock_gps", "28.6139N, 77.2090E"),
        fine_amount=fine_amount, speed=0, evidence_paths=[], status="unpaid"
    )
    
    return {
        "case_id": case_id, "plate": plate, "violation_type": primary_violation,
        "violations": violations, "timestamp": timestamp, "fine_total": fine_amount
    }

@app.on_event("startup")
def startup_event():
    init_db()
    seed_mock_data()
    print("AutoSentinel backend is running.")

@app.get("/")
def root(): return {"app": "AutoSentinel", "status": "running", "docs": "/docs"}

@app.get("/violations")
def violations(date: Optional[str] = Query(default=None), type: Optional[str] = Query(default=None), plate: Optional[str] = Query(default=None)):
    return get_all_violations(date=date, violation_type=type, plate=plate)

@app.get("/stats")
def stats(): return get_stats()

@app.get("/simulate-violation")
def simulate_violation(): return {"success": True}

@app.post("/dispute/{case_id}")
def dispute(case_id: str, payload: DisputeRequest = Body(...)):
    reason = payload.reason.strip()
    if not reason: raise HTTPException(status_code=400, detail="Dispute reason cannot be empty")
    dispute_id = insert_dispute(violation_id=case_id, reason=reason)
    if dispute_id is None: raise HTTPException(status_code=404, detail="Violation case not found")
    return {"success": True, "case_id": case_id, "dispute_id": dispute_id, "status": "pending"}

@app.get("/challan/{case_id}")
def challan(case_id: str):
    pdf_path = ensure_challan_exists(case_id)
    if pdf_path is None: raise HTTPException(status_code=404, detail="Violation case not found")
    path = Path(pdf_path)
    if not path.exists(): raise HTTPException(status_code=500, detail="Challan could not be generated")
    return FileResponse(path=str(path), media_type="application/pdf", filename=f"challan_{case_id}.pdf")

@app.websocket("/live-feed")
async def live_feed(websocket: WebSocket):
    await websocket.accept()
    camera = cv2.VideoCapture("traffic.mp4")
    
    try:
        from detector import ViolationDetector
        detector = ViolationDetector()
    except Exception as e:
        print(f"Detector failed to load: {e}")
        detector = None
        
    try:
        while True:
            success, frame = camera.read()
            if not success:
                camera.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
                
            alert_data = None
            
            if detector is not None:
                try:
                    ai_results = detector.process_frame(frame)
                    
                    # Pass the dynamic Omni-Cam violations to the Database!
                    if ai_results.get("new_alert"):
                        scanned_plate = ai_results.get("plate", "UNKNOWN")
                        active_violations = ai_results.get("violations", ["helmet"])
                        
                        try:
                            alert_data = create_live_fine(scanned_plate, active_violations)
                        except Exception as db_err:
                            print(f"❌ DATABASE ERROR: {db_err}")
                except Exception as ai_err:
                    print(f"❌ AI ERROR: {ai_err}")
                    
            _, buffer = cv2.imencode('.jpg', frame)
            frame_text = base64.b64encode(buffer).decode('utf-8')
            
            payload = {
                "image": frame_text,
                "alert": alert_data
            }
            
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(0.03)
            
    except WebSocketDisconnect:
        pass
    finally:
        camera.release()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)