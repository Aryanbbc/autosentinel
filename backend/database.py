import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "autosentinel.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            plate TEXT PRIMARY KEY,
            owner_name TEXT NOT NULL,
            contact TEXT NOT NULL,
            vehicle_type TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id TEXT PRIMARY KEY,
            plate TEXT NOT NULL,
            violation_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            location TEXT NOT NULL,
            fine_amount INTEGER NOT NULL,
            speed REAL DEFAULT 0,
            evidence_paths TEXT DEFAULT '',
            status TEXT CHECK(status IN ('unpaid', 'paid', 'disputed')) DEFAULT 'unpaid',
            FOREIGN KEY (plate) REFERENCES vehicles(plate)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS disputes (
            id TEXT PRIMARY KEY,
            violation_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            status TEXT CHECK(status IN ('pending', 'resolved')) DEFAULT 'pending',
            FOREIGN KEY (violation_id) REFERENCES violations(id)
        )
    """)

    conn.commit()
    conn.close()


def insert_vehicle(plate, owner_name, contact, vehicle_type):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO vehicles (
            plate,
            owner_name,
            contact,
            vehicle_type
        )
        VALUES (?, ?, ?, ?)
    """, (plate, owner_name, contact, vehicle_type))

    conn.commit()
    conn.close()


def insert_violation(
    plate,
    violation_type,
    timestamp,
    location,
    fine_amount,
    speed=0,
    evidence_paths="",
    status="unpaid"
):
    violation_id = str(uuid.uuid4())

    if isinstance(evidence_paths, list):
        evidence_paths = ",".join(evidence_paths)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO violations (
            id,
            plate,
            violation_type,
            timestamp,
            location,
            fine_amount,
            speed,
            evidence_paths,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        violation_id,
        plate,
        violation_type,
        timestamp,
        location,
        int(fine_amount),
        float(speed or 0),
        evidence_paths or "",
        status
    ))

    conn.commit()
    conn.close()

    return violation_id


def get_all_violations(date=None, violation_type=None, plate=None):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            violations.id,
            violations.plate,
            vehicles.owner_name,
            vehicles.contact,
            vehicles.vehicle_type,
            violations.violation_type,
            violations.timestamp,
            violations.location,
            violations.fine_amount,
            violations.speed,
            violations.evidence_paths,
            violations.status
        FROM violations
        LEFT JOIN vehicles ON violations.plate = vehicles.plate
        WHERE 1 = 1
    """

    params = []

    if date:
        query += " AND violations.timestamp LIKE ?"
        params.append(f"{date}%")

    if violation_type:
        query += " AND LOWER(violations.violation_type) LIKE ?"
        params.append(f"%{violation_type.lower()}%")

    if plate:
        query += " AND UPPER(violations.plate) = ?"
        params.append(plate.upper())

    query += " ORDER BY violations.timestamp DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    conn.close()
    return [dict(row) for row in rows]


def get_violation_by_id(case_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            violations.id,
            violations.plate,
            vehicles.owner_name,
            vehicles.contact,
            vehicles.vehicle_type,
            violations.violation_type,
            violations.timestamp,
            violations.location,
            violations.fine_amount,
            violations.speed,
            violations.evidence_paths,
            violations.status
        FROM violations
        LEFT JOIN vehicles ON violations.plate = vehicles.plate
        WHERE violations.id = ?
    """, (case_id,))

    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def insert_dispute(violation_id, reason):
    violation = get_violation_by_id(violation_id)

    if violation is None:
        return None

    dispute_id = str(uuid.uuid4())
    submitted_at = datetime.now().isoformat(timespec="seconds")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO disputes (
            id,
            violation_id,
            reason,
            submitted_at,
            status
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        dispute_id,
        violation_id,
        reason,
        submitted_at,
        "pending"
    ))

    cursor.execute("""
        UPDATE violations
        SET status = 'disputed'
        WHERE id = ?
    """, (violation_id,))

    conn.commit()
    conn.close()

    return dispute_id


def get_stats():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS total FROM violations")
    total_violations = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT violation_type, COUNT(*) AS count
        FROM violations
        GROUP BY violation_type
        ORDER BY count DESC
    """)

    by_type = {
        row["violation_type"]: row["count"]
        for row in cursor.fetchall()
    }

    cursor.execute("""
        SELECT COALESCE(SUM(fine_amount), 0) AS total
        FROM violations
        WHERE status = 'paid'
    """)

    total_fines_collected = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT plate, COUNT(*) AS count
        FROM violations
        GROUP BY plate
        ORDER BY count DESC
        LIMIT 10
    """)

    top_offenders = [
        {
            "plate": row["plate"],
            "count": row["count"]
        }
        for row in cursor.fetchall()
    ]

    conn.close()

    return {
        "total_violations": total_violations,
        "by_type": by_type,
        "total_fines_collected": total_fines_collected,
        "top_offenders": top_offenders
    }


def seed_mock_data():
    init_db()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS count FROM violations")
    existing_count = cursor.fetchone()["count"]

    if existing_count >= 20:
        conn.close()
        return

    vehicles = [
        ("DL8CAF4321", "Amit Verma", "+919810000001", "Car"),
        ("MH12AB1234", "Rahul Sharma", "+919810000002", "Car"),
        ("KA05MN9087", "Priya Nair", "+919810000003", "Scooter"),
        ("UP16BT7788", "Sandeep Yadav", "+919810000004", "Bike"),
        ("HR26DK9090", "Neha Singh", "+919810000005", "Car"),
        ("RJ14CP3344", "Vikram Rathore", "+919810000006", "Truck"),
        ("GJ01KL2211", "Mehul Patel", "+919810000007", "Car"),
        ("TN09AR5678", "Karthik Raj", "+919810000008", "Bike"),
        ("WB20EF1122", "Ananya Bose", "+919810000009", "Scooter"),
        ("PB10GH7789", "Harpreet Gill", "+919810000010", "Car"),
        ("DL3SAY4567", "Rohit Malhotra", "+919810000011", "Bike"),
        ("MH04DE9091", "Sneha Kulkarni", "+919810000012", "Car"),
        ("KA01HG2200", "Arjun Rao", "+919810000013", "Car"),
        ("TS07FR8899", "Nikhil Reddy", "+919810000014", "Bike"),
        ("KL11BC4455", "Fahad Khan", "+919810000015", "Scooter"),
        ("CH01AA1001", "Ishita Kapoor", "+919810000016", "Car"),
        ("MP09ZZ4321", "Aakash Jain", "+919810000017", "Truck"),
        ("AP31CV6789", "Sai Teja", "+919810000018", "Bike"),
        ("OD02TR1357", "Ramesh Das", "+919810000019", "Car"),
        ("BR01PQ2468", "Manish Kumar", "+919810000020", "Auto")
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO vehicles (
            plate,
            owner_name,
            contact,
            vehicle_type
        )
        VALUES (?, ?, ?, ?)
    """, vehicles)

    fine_map = {
        "seatbelt": 1000,
        "phone": 5000,
        "speed": 2000,
        "helmet": 1000,
        "wrong_way": 5000,
        "drowsiness": 2000
    }

    violation_types = [
        "speed",
        "seatbelt",
        "phone",
        "helmet",
        "wrong_way",
        "speed",
        "phone",
        "helmet",
        "seatbelt",
        "speed",
        "wrong_way",
        "phone",
        "helmet",
        "speed",
        "seatbelt",
        "wrong_way",
        "drowsiness",
        "phone",
        "helmet",
        "seatbelt"
    ]

    statuses = [
        "unpaid",
        "paid",
        "unpaid",
        "disputed",
        "unpaid",
        "paid",
        "unpaid",
        "unpaid",
        "paid",
        "unpaid",
        "disputed",
        "paid",
        "unpaid",
        "unpaid",
        "paid",
        "unpaid",
        "unpaid",
        "paid",
        "unpaid",
        "unpaid"
    ]

    base_time = datetime.now().replace(microsecond=0)

    for index, vehicle in enumerate(vehicles):
        plate_number = vehicle[0]
        violation_type = violation_types[index]
        timestamp = (base_time - timedelta(hours=index * 4)).isoformat()
        speed = 0

        if violation_type == "speed":
            speed = 68 + (index % 5) * 6

        evidence_paths = ",".join([
            f"evidence/{plate_number}_{violation_type}_before.jpg",
            f"evidence/{plate_number}_{violation_type}_violation.jpg",
            f"evidence/{plate_number}_{violation_type}_after.jpg"
        ])

        cursor.execute("""
            INSERT INTO violations (
                id,
                plate,
                violation_type,
                timestamp,
                location,
                fine_amount,
                speed,
                evidence_paths,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            plate_number,
            violation_type,
            timestamp,
            "28.6139N, 77.2090E",
            fine_map[violation_type],
            speed,
            evidence_paths,
            statuses[index]
        ))

    conn.commit()
    conn.close()