from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.asynchronous.database import AsyncDatabase

from ..config import settings
from ..deps import CurrentUser, DbDep, get_current_user, require_roles
from ..schemas import (
    DueRow,
    LedgerResponse,
    PaymentCreate,
    PaymentListResponse,
    PaymentOut,
    ReceiptResponse,
)
from ..services.fees import summarise
from ..services.payments import create_payment
from ..services.payments import classroom_name as _classroom_name
from ..services.payments import day_end as _day_end
from ..services.payments import day_start as _day_start
from ..services.payments import paid_total as _paid_total
from ..services.receipt_pdf import build_receipt_pdf
from ..utils import (
    amount_in_words,
    money,
    now_utc,
    person_name,
    serialize,
    title_name,
    to_object_id,
)

router = APIRouter(prefix="/api/fees", tags=["fees"], dependencies=[Depends(get_current_user)])

ManageOnly = Depends(require_roles("admin", "staff"))

SCHOOL = {
    "name": settings.school_full_name,
    "trust": settings.school_trust,
    "tagline": settings.school_tagline,
    "address": settings.school_address,
    "phone": settings.school_phone,
    "email": settings.school_email,
    "website": settings.school_website,
    "currency": settings.currency_symbol,
    # The on-screen receipt mirrors the PDF: when the banner exists it replaces
    # the composed header rather than sitting above a duplicate of itself.
    "letterhead_file": settings.letterhead_filename,
}


def _public_payment(doc: dict | None) -> dict | None:
    """Serialise a receipt, proper-casing the name copied onto it at the time.

    Receipts written before names were normalised still hold whatever case was
    typed at the desk, and a receipt is the one document a parent keeps.
    """
    out = serialize(doc)
    if out and out.get("student_name"):
        out["student_name"] = title_name(out["student_name"])
    return out


async def _student_or_404(db: AsyncDatabase, student_id: str) -> dict:
    doc = await db.students.find_one({"_id": to_object_id(student_id, "student id")})
    if doc is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return doc


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #
@router.get("/ledger/{student_id}", response_model=LedgerResponse)
async def student_ledger(student_id: str, db: DbDep):
    student = await _student_or_404(db, student_id)
    payments = (
        await db.payments.find({"student_id": student_id}).sort("paid_on", -1).to_list(500)
    )
    paid = money(sum(p["amount"] for p in payments if not p.get("cancelled")))
    override = student.get("next_due_override")
    summary = summarise(student.get("fee_plan"), paid, override)

    return {
        "student_id": student_id,
        "next_due_override": override,
        "student_name": person_name(student.get("first_name"), student.get("last_name")),
        "admission_no": student.get("admission_no", ""),
        "classroom_name": await _classroom_name(db, student.get("classroom_id")),
        **summary,
        "payments": [_public_payment(p) for p in payments],
    }


# --------------------------------------------------------------------------- #
# Payments / receipts
# --------------------------------------------------------------------------- #
@router.post("/payments", response_model=PaymentOut,
             status_code=status.HTTP_201_CREATED, dependencies=[ManageOnly])
async def collect_payment(payload: PaymentCreate, db: DbDep, user: CurrentUser):
    student = await _student_or_404(db, payload.student_id)
    return await create_payment(
        db,
        student,
        amount=payload.amount,
        mode=payload.mode.value,
        paid_on=payload.paid_on,
        reference=payload.reference,
        remarks=payload.remarks,
        items=[i.model_dump() for i in payload.items] if payload.items else None,
        particulars=payload.particulars,
        collected_by=user.get("name"),
        collected_by_id=user.get("id"),
        next_due_date=payload.next_due_date,
    )


@router.get("/payments", response_model=PaymentListResponse)
async def list_payments(
    db: DbDep,
    student_id: str | None = None,
    mode: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    include_cancelled: bool = True,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    query: dict = {}
    if student_id:
        query["student_id"] = student_id
    if mode:
        query["mode"] = mode
    if not include_cancelled:
        query["cancelled"] = {"$ne": True}
    if date_from or date_to:
        window: dict = {}
        if date_from:
            window["$gte"] = _day_start(date_from)
        if date_to:
            window["$lte"] = _day_end(date_to)
        query["paid_on"] = window
    if search:
        rx = {"$regex": search.strip(), "$options": "i"}
        query["$or"] = [
            {"receipt_no": rx},
            {"student_name": rx},
            {"admission_no": rx},
            {"reference": rx},
        ]

    total = await db.payments.count_documents(query)
    cursor = (
        db.payments.find(query)
        .sort("paid_on", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    docs = await cursor.to_list(page_size)

    agg = await db.payments.aggregate(
        [
            {"$match": {**query, "cancelled": {"$ne": True}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
    )
    totals = await agg.to_list(1)

    return {
        "items": [_public_payment(d) for d in docs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_amount": money(totals[0]["total"]) if totals else 0.0,
    }


async def _payment_or_404(db: AsyncDatabase, payment_id: str) -> dict:
    doc = await db.payments.find_one({"_id": to_object_id(payment_id, "payment id")})
    if doc is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return doc


@router.get("/payments/{payment_id}", response_model=PaymentOut)
async def get_payment(payment_id: str, db: DbDep):
    return _public_payment(await _payment_or_404(db, payment_id))


@router.post("/payments/{payment_id}/cancel", response_model=PaymentOut,
             dependencies=[Depends(require_roles("admin"))])
async def cancel_payment(payment_id: str, db: DbDep, reason: str = Query(min_length=3)):
    doc = await _payment_or_404(db, payment_id)
    if doc.get("cancelled"):
        raise HTTPException(status_code=400, detail="This receipt is already cancelled")
    updated = await db.payments.find_one_and_update(
        {"_id": doc["_id"]},
        {"$set": {"cancelled": True, "cancel_reason": reason, "cancelled_at": now_utc()}},
        return_document=True,
    )
    return _public_payment(updated)


async def _receipt_context(db: AsyncDatabase, payment_id: str) -> tuple[dict, dict]:
    payment = await _payment_or_404(db, payment_id)
    student = await db.students.find_one({"_id": to_object_id(payment["student_id"])})
    plan = (student or {}).get("fee_plan") or {}
    paid = await _paid_total(db, payment["student_id"])
    ledger = summarise(plan, paid, (student or {}).get("next_due_override"))
    return payment, ledger


@router.get("/receipts/{payment_id}", response_model=ReceiptResponse)
async def receipt_details(payment_id: str, db: DbDep):
    payment, ledger = await _receipt_context(db, payment_id)
    return {
        "payment": _public_payment(payment),
        "school": SCHOOL,
        "amount_in_words": amount_in_words(payment["amount"]),
        "total_paid": ledger["total_paid"],
        "net_payable": ledger["net_payable"],
        "balance": ledger["balance"],
    }


@router.get("/receipts/{payment_id}/pdf")
async def receipt_pdf(payment_id: str, db: DbDep):
    payment, ledger = await _receipt_context(db, payment_id)
    pdf = build_receipt_pdf(payment, ledger)
    filename = payment["receipt_no"].replace("/", "-") + ".pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
@router.get("/dues", response_model=list[DueRow])
async def outstanding_dues(
    db: DbDep,
    classroom_id: str | None = None,
    only_overdue: bool = False,
    limit: int = Query(default=500, ge=1, le=2000),
):
    query: dict = {"status": "active"}
    if classroom_id:
        query["classroom_id"] = classroom_id
    students = await db.students.find(query).to_list(limit)

    cursor = await db.payments.aggregate(
        [
            {"$match": {"cancelled": {"$ne": True}}},
            {"$group": {"_id": "$student_id", "total": {"$sum": "$amount"}}},
        ]
    )
    paid_map = {row["_id"]: money(row["total"]) for row in await cursor.to_list(5000)}
    class_names = {
        str(c["_id"]): c["name"] for c in await db.classrooms.find({}, {"name": 1}).to_list(200)
    }

    rows: list[dict] = []
    for student in students:
        sid = str(student["_id"])
        summary = summarise(
            student.get("fee_plan"),
            paid_map.get(sid, 0.0),
            student.get("next_due_override"),
        )
        if summary["balance"] <= 0.01:
            continue
        if only_overdue and summary["overdue_amount"] <= 0.01:
            continue
        next_due = summary.get("next_due")
        rows.append(
            {
                "student_id": sid,
                "admission_no": student.get("admission_no", ""),
                "student_name": person_name(student.get("first_name"), student.get("last_name")),
                "classroom_name": class_names.get(student.get("classroom_id") or ""),
                "guardian_phone": (student.get("guardian") or {}).get("primary_phone"),
                "net_payable": summary["net_payable"],
                "total_paid": summary["total_paid"],
                "balance": summary["balance"],
                "overdue_amount": summary["overdue_amount"],
                "next_due_date": next_due["due_date"] if next_due else None,
            }
        )

    rows.sort(key=lambda r: (-r["overdue_amount"], -r["balance"]))
    return rows


@router.get("/summary")
async def collection_summary(
    db: DbDep,
    date_from: date | None = None,
    date_to: date | None = None,
):
    today = date.today()
    start = date_from or (today - timedelta(days=180))
    end = date_to or today
    match = {
        "cancelled": {"$ne": True},
        "paid_on": {"$gte": _day_start(start), "$lte": _day_end(end)},
    }

    by_month_cursor = await db.payments.aggregate(
        [
            {"$match": match},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m", "date": "$paid_on"}},
                    "amount": {"$sum": "$amount"},
                    "receipts": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]
    )
    by_mode_cursor = await db.payments.aggregate(
        [
            {"$match": match},
            {"$group": {"_id": "$mode", "amount": {"$sum": "$amount"}, "receipts": {"$sum": 1}}},
            {"$sort": {"amount": -1}},
        ]
    )
    by_class_cursor = await db.payments.aggregate(
        [
            {"$match": match},
            {
                "$group": {
                    "_id": {"$ifNull": ["$classroom_name", "Unassigned"]},
                    "amount": {"$sum": "$amount"},
                    "receipts": {"$sum": 1},
                }
            },
            {"$sort": {"amount": -1}},
        ]
    )

    def shape(rows):
        return [
            {"key": r["_id"], "amount": money(r["amount"]), "receipts": r["receipts"]}
            for r in rows
        ]

    by_month = shape(await by_month_cursor.to_list(100))
    return {
        "date_from": start,
        "date_to": end,
        "total_collected": money(sum(r["amount"] for r in by_month)),
        "total_receipts": sum(r["receipts"] for r in by_month),
        "by_month": by_month,
        "by_mode": shape(await by_mode_cursor.to_list(20)),
        "by_class": shape(await by_class_cursor.to_list(50)),
    }
