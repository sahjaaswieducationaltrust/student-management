"""Receipt creation, shared by the fee counter and the enrolment form.

Both entry points must number receipts, allocate the money to instalments and
compute the running balance in exactly the same way, so that logic lives here.
"""

from datetime import date, datetime, time, timezone
from typing import Any

from fastapi import HTTPException
from pymongo.asynchronous.database import AsyncDatabase

from ..config import settings
from ..utils import money, now_utc, person_name, serialize, to_object_id
from .counters import next_receipt_no
from .fees import auto_allocate_items


def day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def day_end(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


async def classroom_name(db: AsyncDatabase, classroom_id: str | None) -> str | None:
    if not classroom_id:
        return None
    doc = await db.classrooms.find_one(
        {"_id": to_object_id(classroom_id, "classroom id")}, {"name": 1}
    )
    return doc["name"] if doc else None


async def paid_total(db: AsyncDatabase, student_id: str, exclude_id=None) -> float:
    """Sum of every non-cancelled receipt for a student."""
    match: dict = {"student_id": student_id, "cancelled": {"$ne": True}}
    if exclude_id is not None:
        match["_id"] = {"$ne": exclude_id}
    cursor = await db.payments.aggregate(
        [{"$match": match}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
    )
    rows = await cursor.to_list(1)
    return money(rows[0]["total"]) if rows else 0.0


async def paid_totals(db: AsyncDatabase, student_ids: list[str]) -> dict[str, float]:
    """Paid totals for many students in one round trip (used by list views)."""
    if not student_ids:
        return {}
    cursor = await db.payments.aggregate(
        [
            {"$match": {"student_id": {"$in": student_ids}, "cancelled": {"$ne": True}}},
            {"$group": {"_id": "$student_id", "total": {"$sum": "$amount"}}},
        ]
    )
    return {row["_id"]: money(row["total"]) for row in await cursor.to_list(len(student_ids))}


async def create_payment(
    db: AsyncDatabase,
    student: dict[str, Any],
    *,
    amount: float,
    mode: str = "cash",
    paid_on: date | None = None,
    reference: str | None = None,
    remarks: str | None = None,
    items: list[dict[str, Any]] | None = None,
    particulars: str | None = None,
    collected_by: str | None = None,
    collected_by_id: str | None = None,
    next_due_date: date | None = None,
) -> dict[str, Any]:
    """Record a payment and issue its receipt. Returns the serialised receipt."""
    amount = money(amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")

    plan = student.get("fee_plan") or {}
    installments = plan.get("installments", [])
    student_id = str(student["_id"])
    already_paid = await paid_total(db, student_id)

    if items:
        item_total = money(sum(i["amount"] for i in items))
        if abs(item_total - amount) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=f"Line items total {item_total} does not match the amount {amount}",
            )
    elif particulars and particulars.strip():
        # The desk said what this is for. That reads far better on a receipt
        # than a schedule-derived label, especially when the whole year sits in
        # one instalment and every payment would otherwise say the same thing.
        items = [{"name": particulars.strip()[:120], "amount": amount}]
    else:
        items = auto_allocate_items(installments, already_paid, amount)

    academic_year = plan.get("academic_year") or settings.academic_year
    net_payable = money(plan.get("net_payable", 0))

    doc = {
        "receipt_no": await next_receipt_no(db, academic_year),
        "student_id": student_id,
        "student_name": person_name(student.get("first_name"), student.get("last_name")),
        "admission_no": student.get("admission_no", ""),
        "classroom_name": await classroom_name(db, student.get("classroom_id")),
        "academic_year": academic_year,
        "amount": amount,
        "mode": mode,
        "reference": reference,
        "remarks": remarks,
        "items": items,
        "paid_on": day_start(paid_on) if paid_on else now_utc(),
        "collected_by": collected_by,
        "collected_by_id": collected_by_id,
        "cancelled": False,
        "balance_after": money(net_payable - (already_paid + amount)),
        "created_at": now_utc(),
    }
    result = await db.payments.insert_one(doc)
    doc["_id"] = result.inserted_id

    # The desk often agrees the next instalment date while taking this one.
    # It lives on the student, not the receipt, because it describes what is
    # still owed rather than what was just collected.
    if next_due_date is not None:
        await db.students.update_one(
            {"_id": student["_id"]},
            {"$set": {"next_due_override": day_start(next_due_date), "updated_at": now_utc()}},
        )

    return serialize(doc)
