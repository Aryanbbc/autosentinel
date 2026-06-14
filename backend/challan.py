import json
from datetime import datetime, timedelta
from pathlib import Path

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle
)


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
CONFIG_PATH = BASE_DIR / "config.json"
CHALLAN_DIR = PROJECT_ROOT / "challans"


def load_config():
    default_config = {
        "camera_unit_id": "CAM-DL-001",
        "mock_gps": "28.6139N, 77.2090E"
    }

    if not CONFIG_PATH.exists():
        return default_config

    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        loaded = json.load(file)

    return {**default_config, **loaded}


def register_font():
    possible_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "C:/Windows/Fonts/arial.ttf"
    ]

    for font_path in possible_fonts:
        if Path(font_path).exists():
            pdfmetrics.registerFont(TTFont("AutoSentinelFont", font_path))
            return "AutoSentinelFont"

    return "Helvetica"


def parse_timestamp(timestamp):
    if isinstance(timestamp, datetime):
        return timestamp

    if not timestamp:
        return datetime.now()

    value = str(timestamp).replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass

    for fmt in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S"
    ]:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    return datetime.now()


def make_qr_drawing(data, size=82):
    qr = QrCodeWidget(data)
    bounds = qr.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]

    drawing = Drawing(
        size,
        size,
        transform=[
            size / width,
            0,
            0,
            size / height,
            0,
            0
        ]
    )

    drawing.add(qr)
    return drawing


def make_table(data, col_widths):
    table = Table(data, colWidths=col_widths)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F9FAFB")),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#111827")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    return table


def generate_challan(violation_data, evidence_paths=None):
    CHALLAN_DIR.mkdir(parents=True, exist_ok=True)

    config = load_config()
    font_name = register_font()

    case_id = str(violation_data.get("case_id") or violation_data.get("id") or "UNKNOWN")
    plate = str(violation_data.get("plate", "UNKNOWN"))
    owner_name = str(violation_data.get("owner_name", "Unknown"))
    contact = str(violation_data.get("contact", "Not Available"))
    vehicle_type = str(violation_data.get("vehicle_type", "Unknown"))
    violation_type = str(violation_data.get("violation_type", "Unknown")).replace("_", " ").title()
    location = str(violation_data.get("location", config["mock_gps"]))
    fine_amount = int(violation_data.get("fine_amount", 0))
    speed = violation_data.get("speed", 0)
    camera_id = config.get("camera_unit_id", "CAM-DL-001")

    violation_dt = parse_timestamp(violation_data.get("timestamp"))
    due_dt = violation_dt + timedelta(days=30)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payment_url = f"https://autosentinel.gov.in/pay/{case_id}"

    pdf_path = CHALLAN_DIR / f"challan_{case_id}.pdf"

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=28,
        bottomMargin=28
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "AutoSentinelTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=colors.HexColor("#111827"),
        leading=18
    )

    subtitle_style = ParagraphStyle(
        "AutoSentinelSubtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
        textColor=colors.HexColor("#374151")
    )

    right_style = ParagraphStyle(
        "AutoSentinelRight",
        parent=styles["Normal"],
        alignment=TA_RIGHT,
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#111827")
    )

    section_style = ParagraphStyle(
        "AutoSentinelSection",
        parent=styles["Heading2"],
        alignment=TA_LEFT,
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=colors.HexColor("#111827"),
        spaceBefore=10,
        spaceAfter=6
    )

    normal_style = ParagraphStyle(
        "AutoSentinelNormal",
        parent=styles["Normal"],
        alignment=TA_LEFT,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#111827")
    )

    fine_style = ParagraphStyle(
        "AutoSentinelFine",
        parent=styles["Normal"],
        alignment=TA_LEFT,
        fontName=font_name,
        fontSize=17,
        leading=22,
        textColor=colors.red
    )

    footer_style = ParagraphStyle(
        "AutoSentinelFooter",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#4B5563")
    )

    story = []

    flag_bar = Table(
        [["", "", ""]],
        colWidths=[doc.width / 3, doc.width / 3, doc.width / 3],
        rowHeights=[9]
    )

    flag_bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#FF9933")),
        ("BACKGROUND", (1, 0), (1, 0), colors.white),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#138808")),
        ("BOX", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
    ]))

    story.append(flag_bar)
    story.append(Spacer(1, 8))

    header_left = [
        Paragraph("GOVERNMENT OF INDIA — TRAFFIC VIOLATION NOTICE", title_style),
        Paragraph("Issued under Motor Vehicles Act, 1988", subtitle_style)
    ]

    header_right = Paragraph(
        f"Camera Unit ID: {camera_id}<br/>Case ID: {case_id}",
        right_style
    )

    header_table = Table(
        [[header_left, header_right]],
        colWidths=[doc.width * 0.70, doc.width * 0.30]
    )

    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP")
    ]))

    story.append(header_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph("1. Vehicle Details", section_style))

    story.append(make_table(
        [
            ["License Plate", "Vehicle Type", "Owner Name", "Contact"],
            [plate, vehicle_type, owner_name, contact]
        ],
        [
            doc.width * 0.22,
            doc.width * 0.20,
            doc.width * 0.32,
            doc.width * 0.26
        ]
    ))

    story.append(Paragraph("2. Violation Details", section_style))

    speed_text = "N/A"

    try:
        if float(speed) > 0:
            speed_text = f"{float(speed):.1f} km/h"
    except (TypeError, ValueError):
        speed_text = "N/A"

    story.append(make_table(
        [
            ["Violation Type", "Date & Time", "Location GPS", "Speed"],
            [
                violation_type,
                violation_dt.strftime("%Y-%m-%d %H:%M:%S"),
                location,
                speed_text
            ]
        ],
        [
            doc.width * 0.24,
            doc.width * 0.27,
            doc.width * 0.32,
            doc.width * 0.17
        ]
    ))

    story.append(Paragraph("3. Fine Details", section_style))

    fine_text = f"Fine Amount: ₹{fine_amount}"

    if font_name == "Helvetica":
        fine_text = f"Fine Amount: Rs. {fine_amount}"

    fine_table = Table(
        [[
            Paragraph(fine_text, fine_style),
            Paragraph(
                f"<b>Due Date:</b> {due_dt.strftime('%Y-%m-%d')}<br/>"
                f"<b>Payment Link:</b> {payment_url}",
                normal_style
            )
        ]],
        colWidths=[doc.width * 0.38, doc.width * 0.62]
    )

    fine_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#EF4444")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))

    story.append(fine_table)

    story.append(Paragraph("4. Evidence Record", section_style))

    if evidence_paths is None:
        evidence_paths = violation_data.get("evidence_paths", "")

    if isinstance(evidence_paths, str):
        evidence_paths = [
            item.strip()
            for item in evidence_paths.split(",")
            if item.strip()
        ]

    evidence_paths = evidence_paths or [
        f"camera://{camera_id}/frame-before/{case_id}",
        f"camera://{camera_id}/frame-violation/{case_id}",
        f"camera://{camera_id}/frame-after/{case_id}"
    ]

    evidence_rows = [["Frame", "Evidence Reference"]]

    captions = ["Frame 1 - Before", "Frame 2 - Violation", "Frame 3 - After"]

    for index in range(3):
        evidence_rows.append([
            captions[index],
            evidence_paths[index] if index < len(evidence_paths) else f"camera://{camera_id}/frame-{index + 1}/{case_id}"
        ])

    story.append(make_table(
        evidence_rows,
        [
            doc.width * 0.28,
            doc.width * 0.72
        ]
    ))

    story.append(Spacer(1, 12))

    qr_drawing = make_qr_drawing(payment_url)

    dispute_text = Paragraph(
        "<b>Dispute Instructions:</b><br/>"
        "To dispute this challan, visit autosentinel.gov.in/dispute and enter the Case ID. "
        "Disputes must be submitted before the due date with a clear reason and supporting evidence.",
        normal_style
    )

    qr_table = Table(
        [[dispute_text, qr_drawing]],
        colWidths=[doc.width * 0.76, doc.width * 0.24]
    )

    qr_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(qr_table)
    story.append(Spacer(1, 12))

    footer = (
        "This is a system-generated notice. No signature required.<br/>"
        f"Case ID: {case_id} | Camera ID: {camera_id} | Generated At: {generated_at}"
    )

    story.append(Paragraph(footer, footer_style))

    doc.build(story)

    return str(pdf_path)