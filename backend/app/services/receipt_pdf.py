"""Printable A4 fee receipt (ReportLab)."""

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..config import settings
from ..utils import amount_in_words, money, payment_mode_label

INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
BRAND = colors.HexColor("#0054a5")  # Hello Kids blue
LIME = colors.HexColor("#6f8a1c")  # readable version of the logo's lime
LINE = colors.HexColor("#d8dce6")
SOFT = colors.HexColor("#eaf1f8")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    return {
        "school": ParagraphStyle(
            "school", parent=base, fontName="Helvetica-Bold", fontSize=17,
            textColor=BRAND, alignment=TA_CENTER, leading=21,
        ),
        "sub": ParagraphStyle(
            "sub", parent=base, fontSize=8.5, textColor=MUTED,
            alignment=TA_CENTER, leading=12,
        ),
        "tagline": ParagraphStyle(
            "tagline", parent=base, fontName="Helvetica-Bold", fontSize=7.5,
            textColor=LIME, alignment=TA_CENTER, leading=11,
        ),
        "title": ParagraphStyle(
            "title", parent=base, fontName="Helvetica-Bold", fontSize=11.5,
            textColor=INK, alignment=TA_CENTER, leading=16,
        ),
        "label": ParagraphStyle("label", parent=base, fontSize=8, textColor=MUTED),
        "value": ParagraphStyle(
            "value", parent=base, fontName="Helvetica-Bold", fontSize=9.5, textColor=INK
        ),
        "cell": ParagraphStyle("cell", parent=base, fontSize=9, textColor=INK),
        "right": ParagraphStyle("right", parent=base, fontSize=9, alignment=TA_RIGHT),
        "note": ParagraphStyle("note", parent=base, fontSize=8, textColor=MUTED, leading=11),
        "words": ParagraphStyle(
            "words", parent=base, fontName="Helvetica-Oblique", fontSize=9, textColor=INK
        ),
    }


def _rupees(value: float) -> str:
    return f"Rs. {money(value):,.2f}"


def _pair(st: dict, label: str, value: str) -> list:
    return [Paragraph(label, st["label"]), Paragraph(value or "-", st["value"])]


def build_receipt_pdf(payment: dict[str, Any], ledger: dict[str, Any]) -> bytes:
    st = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Receipt {payment['receipt_no']}",
        author=settings.school_full_name,
    )
    content_width = doc.width
    flow: list = []

    # ---------------- header ----------------
    contact = f"Phone: {settings.school_phone} &nbsp;|&nbsp; {settings.school_email}"
    if settings.school_website:
        contact += f" &nbsp;|&nbsp; {settings.school_website}"

    masthead = [
        Paragraph(settings.school_full_name, st["school"]),
        Paragraph(settings.school_tagline, st["tagline"]),
        Spacer(1, 3),
        Paragraph(settings.school_address, st["sub"]),
        Paragraph(contact, st["sub"]),
    ]

    logo = settings.logo_path
    if logo:
        # Square logo, kept small so the 90px source stays crisp in print.
        mark = Image(str(logo), width=19 * mm, height=19 * mm, kind="proportional")
        header = Table(
            [[mark, masthead, ""]],
            colWidths=[22 * mm, content_width - 44 * mm, 22 * mm],
        )
        header.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        flow.append(header)
    else:
        flow.extend(masthead)

    flow.append(Spacer(1, 7))
    flow.append(HRFlowable(width="100%", thickness=1.6, color=BRAND, spaceAfter=8))

    cancelled = payment.get("cancelled")
    heading = "FEE RECEIPT (CANCELLED)" if cancelled else "FEE RECEIPT"
    title_tbl = Table([[Paragraph(heading, st["title"])]], colWidths=[content_width])
    title_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fee2e2") if cancelled else SOFT),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    flow.append(title_tbl)
    flow.append(Spacer(1, 10))

    # ---------------- meta ----------------
    paid_on = payment.get("paid_on")
    paid_on_txt = paid_on.strftime("%d %b %Y") if hasattr(paid_on, "strftime") else str(paid_on)
    mode_txt = payment_mode_label(payment.get("mode"))

    meta_rows = [
        _pair(st, "Receipt No.", payment.get("receipt_no", "")) + _pair(st, "Date", paid_on_txt),
        _pair(st, "Admission No.", payment.get("admission_no", ""))
        + _pair(st, "Academic Year", payment.get("academic_year", "")),
        _pair(st, "Student Name", payment.get("student_name", ""))
        + _pair(st, "Class", payment.get("classroom_name") or "-"),
        _pair(st, "Payment Mode", mode_txt)
        + _pair(st, "Reference", payment.get("reference") or "-"),
    ]
    col = content_width / 4
    meta = Table(meta_rows, colWidths=[col * 0.8, col * 1.2, col * 0.8, col * 1.2])
    meta.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LINEBEFORE", (2, 0), (2, -1), 0.4, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    flow.append(meta)
    flow.append(Spacer(1, 12))

    # ---------------- particulars ----------------
    items = payment.get("items") or [{"name": "Fee payment", "amount": payment.get("amount", 0)}]
    table_data = [
        [
            Paragraph("<b>#</b>", st["cell"]),
            Paragraph("<b>Particulars</b>", st["cell"]),
            Paragraph("<b>Amount</b>", st["right"]),
        ]
    ]
    for idx, item in enumerate(items, start=1):
        table_data.append(
            [
                Paragraph(str(idx), st["cell"]),
                Paragraph(str(item.get("name", "Fee")), st["cell"]),
                Paragraph(_rupees(item.get("amount", 0)), st["right"]),
            ]
        )
    table_data.append(
        [
            "",
            Paragraph("<b>Total Paid</b>", st["cell"]),
            Paragraph(f"<b>{_rupees(payment.get('amount', 0))}</b>", st["right"]),
        ]
    )

    particulars = Table(
        table_data, colWidths=[content_width * 0.08, content_width * 0.62, content_width * 0.30]
    )
    particulars.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, -1), (-1, -1), SOFT),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    flow.append(particulars)
    flow.append(Spacer(1, 8))

    flow.append(
        Paragraph(
            f"<b>In words:</b> {amount_in_words(payment.get('amount', 0))}", st["words"]
        )
    )
    flow.append(Spacer(1, 10))

    # ---------------- ledger summary ----------------
    summary = Table(
        [
            [
                Paragraph("Total fee payable", st["cell"]),
                Paragraph(_rupees(ledger.get("net_payable", 0)), st["right"]),
            ],
            [
                Paragraph("Paid till date", st["cell"]),
                Paragraph(_rupees(ledger.get("total_paid", 0)), st["right"]),
            ],
            [
                Paragraph("<b>Balance due</b>", st["cell"]),
                Paragraph(f"<b>{_rupees(ledger.get('balance', 0))}</b>", st["right"]),
            ],
        ],
        colWidths=[content_width * 0.30, content_width * 0.20],
        hAlign="RIGHT",
    )
    summary.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("BACKGROUND", (0, -1), (-1, -1), SOFT),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    flow.append(summary)

    if payment.get("remarks"):
        flow.append(Spacer(1, 10))
        flow.append(Paragraph(f"<b>Remarks:</b> {payment['remarks']}", st["note"]))
    if cancelled:
        flow.append(Spacer(1, 6))
        flow.append(
            Paragraph(
                f"<b>This receipt has been cancelled.</b> {payment.get('cancel_reason') or ''}",
                st["note"],
            )
        )

    flow.append(Spacer(1, 26))
    footer = Table(
        [
            [
                Paragraph(
                    f"Received by: {payment.get('collected_by') or '-'}<br/><br/>"
                    "This is a computer generated receipt.",
                    st["note"],
                ),
                Paragraph(
                    "<br/><br/>_______________________<br/>Authorised Signatory",
                    ParagraphStyle("sig", parent=st["note"], alignment=TA_RIGHT),
                ),
            ]
        ],
        colWidths=[content_width * 0.55, content_width * 0.45],
    )
    footer.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    flow.append(footer)

    doc.build(flow)
    return buffer.getvalue()
