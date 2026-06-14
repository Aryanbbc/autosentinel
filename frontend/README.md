# AutoSentinel 🚦

**AutoSentinel** is an AI-powered traffic enforcement prototype that detects traffic violations using computer vision, estimates speed, reads vehicle plates, stores violations in a database, and generates challan PDFs.

It is designed as a full-stack engineering project combining:

* Computer Vision
* FastAPI backend
* React dashboard
* SQLite database
* PDF challan generation
* Real-time monitoring UI

---

## Screenshots

> Add your screenshots here after running the demo.

### Live Monitor

![Live Monitor Screenshot](screenshots/live-monitor.png)

### Violations Log

![Violations Log Screenshot](screenshots/violations-log.png)

### Analytics Dashboard

![Analytics Screenshot](screenshots/analytics.png)

### Challan PDF

![Challan Screenshot](screenshots/challan.png)

---

## Project Structure

```txt
autosentinel/
├── backend/
│   ├── main.py
│   ├── detector.py
│   ├── speed.py
│   ├── ocr.py
│   ├── challan.py
│   ├── database.py
│   └── config.json
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── LiveMonitor.jsx
│       │   ├── ViolationsLog.jsx
│       │   ├── Analytics.jsx
│       │   └── DisputePortal.jsx
│       └── App.jsx
├── models/
├── evidence/
├── challans/
├── demo_footage/
├── requirements.txt
├── README.md
└── DEMO.md
```

---

## Features

### AI Detection

AutoSentinel detects:

* Seatbelt violation
* Mobile phone usage
* Overspeeding
* Helmet violation
* Wrong-way violation
* Drowsiness alert

### Vehicle Plate Reading

The OCR module uses EasyOCR and OpenCV preprocessing to read Indian-style number plates.

Example plate format:

```txt
DL8CAF4321
MH12AB1234
KA05MN9087
```

### Challan Generation

When a violation is detected, the backend automatically:

1. Saves evidence frames
2. Inserts violation into SQLite
3. Generates challan PDF
4. Creates QR payment link
5. Prints mock SMS alert to console

### Dashboard

The React frontend provides:

* Live monitoring screen
* Real-time alert feed
* Violation log with filters
* Challan PDF download
* Analytics charts
* Dispute submission portal

---

## Backend Setup

From the project root:

```bash
pip install -r requirements.txt
```

Start the FastAPI backend:

```bash
python backend/main.py
```

Backend runs on:

```txt
http://localhost:8000
```

API docs are available at:

```txt
http://localhost:8000/docs
```

Alternative command if needed:

```bash
uvicorn backend.main:app --reload --port 8000
```

---

## Frontend Setup

Go to the frontend folder:

```bash
cd frontend
```

Install frontend dependencies:

```bash
npm install
```

Start React development server:

```bash
npm start
```

Frontend runs on:

```txt
http://localhost:3000
```

If using Vite instead of Create React App:

```bash
npm run dev
```

---

## Required Frontend Packages

Install these inside the `frontend/` directory:

```bash
npm install axios react-router-dom chart.js react-chartjs-2
```

Tailwind CSS must also be configured in the frontend project.

Install Tailwind:

```bash
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

Example `tailwind.config.js`:

```js
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}"
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

Add this to your CSS file:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

---

## Configuration Guide

All tunable backend values are stored in:

```txt
backend/config.json
```

Example:

```json
{
  "speed_limit_kmh": 60,
  "ear_threshold": 0.25,
  "drowsy_frame_count": 15,
  "fines": {
    "seatbelt": 1000,
    "phone": 5000,
    "speed": 2000,
    "helmet": 1000,
    "wrong_way": 5000
  },
  "camera_unit_id": "CAM-DL-001",
  "mock_gps": "28.6139N, 77.2090E"
}
```

### Config Options

| Field                | Meaning                                                      |
| -------------------- | ------------------------------------------------------------ |
| `speed_limit_kmh`    | Speed limit used for overspeeding detection                  |
| `ear_threshold`      | Eye Aspect Ratio threshold for drowsiness                    |
| `drowsy_frame_count` | Number of consecutive low-EAR frames before drowsiness alert |
| `fines.seatbelt`     | Fine amount for seatbelt violation                           |
| `fines.phone`        | Fine amount for phone usage violation                        |
| `fines.speed`        | Fine amount for overspeeding                                 |
| `fines.helmet`       | Fine amount for helmet violation                             |
| `fines.wrong_way`    | Fine amount for wrong-way violation                          |
| `camera_unit_id`     | Unique camera unit identifier                                |
| `mock_gps`           | Demo GPS location used in challan generation                 |

After editing `config.json`, restart the backend.

---

## API Reference

| Method      | Endpoint                       | Description                                                |
| ----------- | ------------------------------ | ---------------------------------------------------------- |
| `POST`      | `/detect`                      | Upload image frame or base64 frame for violation detection |
| `GET`       | `/violations`                  | Fetch all violations                                       |
| `GET`       | `/violations?date=YYYY-MM-DD`  | Filter violations by date                                  |
| `GET`       | `/violations?type=speed`       | Filter violations by type                                  |
| `GET`       | `/violations?plate=DL8CAF4321` | Filter violations by plate                                 |
| `GET`       | `/challan/{case_id}`           | Download challan PDF                                       |
| `POST`      | `/dispute/{case_id}`           | Submit dispute for a violation                             |
| `GET`       | `/stats`                       | Fetch analytics summary                                    |
| `GET`       | `/simulate-violation`          | Create fake violation for demo                             |
| `WebSocket` | `/live-feed`                   | Stream processed live frames to frontend                   |

---

## Example API Usage

### Simulate Violation

```bash
curl http://localhost:8000/simulate-violation
```

### Get Violations

```bash
curl http://localhost:8000/violations
```

### Submit Dispute

```bash
curl -X POST http://localhost:8000/dispute/YOUR_CASE_ID \
  -H "Content-Type: application/json" \
  -d '{"reason": "The detected vehicle was not mine."}'
```

### Download Challan

Open in browser:

```txt
http://localhost:8000/challan/YOUR_CASE_ID
```

---

## Using a Real Webcam

The `/live-feed` WebSocket endpoint currently opens the default webcam:

```python
camera = cv2.VideoCapture(0)
```

Use this for your laptop webcam.

```python
camera = cv2.VideoCapture(0)
```

For an external USB webcam, try:

```python
camera = cv2.VideoCapture(1)
```

For CCTV / IP camera stream:

```python
camera = cv2.VideoCapture("rtsp://username:password@camera-ip/stream")
```

---

## Using a Video File

Place your video inside:

```txt
demo_footage/
```

Example:

```txt
demo_footage/traffic_demo.mp4
```

Then modify `backend/main.py` inside `/live-feed`:

```python
camera = cv2.VideoCapture("../demo_footage/traffic_demo.mp4")
```

Or use absolute path:

```python
camera = cv2.VideoCapture("/full/path/to/demo_footage/traffic_demo.mp4")
```

Restart backend after changing the video source.

---

## Evidence Storage

Evidence frames are saved in:

```txt
evidence/
```

Example:

```txt
evidence/case_id_frame_1.jpg
evidence/case_id_frame_2.jpg
evidence/case_id_frame_3.jpg
```

These are embedded into the challan PDF.

---

## Challan Storage

Generated challans are saved in:

```txt
challans/
```

Example:

```txt
challans/challan_case_id.pdf
```

---

## Database

AutoSentinel uses SQLite.

Database file:

```txt
backend/autosentinel.db
```

Tables:

* `vehicles`
* `violations`
* `disputes`

Mock data is seeded automatically on first backend startup.

---

## Tech Stack Credits

### Backend

* Python
* FastAPI
* Uvicorn
* OpenCV
* Ultralytics YOLOv8
* MediaPipe
* EasyOCR
* SQLite
* ReportLab
* qrcode
* NumPy
* Pillow

### Frontend

* React
* React Router
* Tailwind CSS
* Axios
* Chart.js
* react-chartjs-2

---

## Important Note

AutoSentinel is a prototype project for learning and portfolio demonstration.

A real traffic enforcement system would require:

* Certified camera hardware
* Government approval
* Secure audit logs
* Tamper-proof evidence storage
* Legal compliance
* Data privacy safeguards
* Official payment gateway integration

This project is built to demonstrate engineering ability, not to issue real government challans.
