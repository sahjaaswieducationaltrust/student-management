import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from ..config import settings
from ..deps import CurrentUser, DbDep, get_current_user, require_roles
from ..schemas import (
    FeePlanAssign,
    StudentCreate,
    StudentCreatedOut,
    StudentListResponse,
    StudentOut,
    StudentUpdate,
)
from ..services.counters import next_admission_no
from ..services.fees import build_fee_plan, summarise
from ..services.payments import create_payment, paid_totals
from ..utils import age_from_dob, encode_dates, money, now_utc, serialize, to_object_id

router = APIRouter(
    prefix="/api/students", tags=["students"], dependencies=[Depends(get_current_user)]
)

ManageOnly = Depends(require_roles("admin", "staff"))


def fee_summary(fee_plan: dict | None, paid: float) -> dict:
    """Compact fee position for list views — total, paid, balance, next due."""
    summary = summarise(fee_plan, paid)
    next_due = summary.get("next_due")
    return {
        "net_payable": summary["net_payable"],
        "total_paid": summary["total_paid"],
        "balance": summary["balance"],
        "overdue_amount": summary["overdue_amount"],
        "next_due_date": next_due["due_date"] if next_due else None,
        "next_due_amount": next_due["balance"] if next_due else 0,
    }


async def enrich(db: AsyncDatabase, doc: dict, paid: float | None = None) -> dict:
    out = serialize(doc)
    out["full_name"] = " ".join(filter(None, [out.get("first_name"), out.get("last_name")]))
    out["age"] = age_from_dob(out.get("date_of_birth"))
    out["classroom_name"] = None
    if out.get("classroom_id"):
        classroom = await db.classrooms.find_one(
            {"_id": to_object_id(out["classroom_id"], "classroom id")}, {"name": 1}
        )
        if classroom:
            out["classroom_name"] = classroom["name"]

    if paid is None:
        totals = await paid_totals(db, [out["id"]])
        paid = totals.get(out["id"], 0.0)
    out["fee_summary"] = fee_summary(doc.get("fee_plan"), paid)
    return out


async def get_student_or_404(db: AsyncDatabase, student_id: str) -> dict:
    doc = await db.students.find_one({"_id": to_object_id(student_id, "student id")})
    if doc is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return doc


@router.get("", response_model=StudentListResponse)
async def list_students(
    db: DbDep,
    search: str | None = None,
    classroom_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    dues: str | None = Query(
        default=None,
        description="'pending' = balance outstanding, 'overdue' = past a due date, 'clear' = fully paid",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    query: dict = {}
    if classroom_id:
        query["classroom_id"] = classroom_id
    if status_filter:
        query["status"] = status_filter
    if search:
        rx = re.compile(re.escape(search.strip()), re.IGNORECASE)
        query["$or"] = [
            {"first_name": rx},
            {"last_name": rx},
            {"admission_no": rx},
            {"guardian.primary_phone": rx},
            {"guardian.father_name": rx},
            {"guardian.mother_name": rx},
        ]

    # Dues are derived from the fee plan and the receipts, not stored on the
    # student, so filtering and totalling by them happens here rather than in
    # the query. A preschool roll is small enough for this to be cheap.
    docs = await db.students.find(query).sort("created_at", -1).to_list(2000)
    paid_map = await paid_totals(db, [str(d["_id"]) for d in docs])

    rows = []
    for doc in docs:
        summary = fee_summary(doc.get("fee_plan"), paid_map.get(str(doc["_id"]), 0.0))
        if dues == "pending" and summary["balance"] <= 0.01:
            continue
        if dues == "overdue" and summary["overdue_amount"] <= 0.01:
            continue
        if dues == "clear" and summary["balance"] > 0.01:
            continue
        rows.append((doc, summary))

    totals = {
        "net_payable": money(sum(s["net_payable"] for _, s in rows)),
        "total_paid": money(sum(s["total_paid"] for _, s in rows)),
        "balance": money(sum(s["balance"] for _, s in rows)),
        "overdue_amount": money(sum(s["overdue_amount"] for _, s in rows)),
    }

    total = len(rows)
    page_rows = rows[(page - 1) * page_size : page * page_size]
    return {
        "items": [
            await enrich(db, doc, paid_map.get(str(doc["_id"]), 0.0)) for doc, _ in page_rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "totals": totals,
    }


@router.post("", response_model=StudentCreatedOut, status_code=status.HTTP_201_CREATED,
             dependencies=[ManageOnly])
async def create_student(payload: StudentCreate, db: DbDep, user: CurrentUser):
    """Enrol a child: profile + agreed fee plan + (optionally) the first instalment."""
    doc = encode_dates(
        payload.model_dump(exclude={"admission_no", "agreed_fee", "fee_note", "initial_payment"})
    )
    doc["admission_no"] = payload.admission_no or await next_admission_no(db)
    doc["admission_date"] = doc.get("admission_date") or encode_dates(now_utc().date())
    doc["created_at"] = now_utc()

    # Fee plan: the class structure sets the standard, the agreed fee overrides it.
    doc["fee_plan"] = None
    components: list[dict] = []
    academic_year = settings.academic_year

    if payload.classroom_id:
        classroom = await db.classrooms.find_one(
            {"_id": to_object_id(payload.classroom_id, "classroom id")}
        )
        if classroom is None:
            raise HTTPException(status_code=400, detail="Classroom not found")
        components = classroom.get("fee_components") or []
        academic_year = classroom.get("academic_year") or settings.academic_year

    if components or payload.agreed_fee is not None:
        doc["fee_plan"] = encode_dates(
            build_fee_plan(
                components,
                academic_year=academic_year,
                agreed_total=payload.agreed_fee,
                discount_reason=payload.fee_note,
            )
        )

    try:
        result = await db.students.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Admission number {doc['admission_no']} already exists",
        )
    doc["_id"] = result.inserted_id

    receipt = None
    if payload.initial_payment:
        initial = payload.initial_payment
        receipt = await create_payment(
            db,
            doc,
            amount=initial.amount,
            mode=initial.mode.value,
            paid_on=initial.paid_on,
            reference=initial.reference,
            remarks=initial.remarks,
            collected_by=user.get("name"),
            collected_by_id=user.get("id"),
        )

    out = await enrich(db, doc)
    out["initial_receipt"] = receipt
    return out


@router.get("/{student_id}", response_model=StudentOut)
async def get_student(student_id: str, db: DbDep):
    return await enrich(db, await get_student_or_404(db, student_id))


@router.patch("/{student_id}", response_model=StudentOut, dependencies=[ManageOnly])
async def update_student(student_id: str, payload: StudentUpdate, db: DbDep):
    updates = encode_dates(payload.model_dump(exclude_none=True))
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if updates.get("classroom_id"):
        exists = await db.classrooms.count_documents(
            {"_id": to_object_id(updates["classroom_id"], "classroom id")}
        )
        if not exists:
            raise HTTPException(status_code=400, detail="Classroom not found")
    updates["updated_at"] = now_utc()

    doc = await db.students.find_one_and_update(
        {"_id": to_object_id(student_id, "student id")},
        {"$set": updates},
        return_document=True,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return await enrich(db, doc)


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_roles("admin"))])
async def delete_student(student_id: str, db: DbDep):
    receipts = await db.payments.count_documents({"student_id": student_id})
    if receipts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{receipts} receipt(s) exist for this student. "
                "Set the status to inactive instead of deleting."
            ),
        )
    result = await db.students.delete_one({"_id": to_object_id(student_id, "student id")})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Student not found")
    await db.attendance.delete_many({"student_id": student_id})


@router.post("/{student_id}/fee-plan", response_model=StudentOut, dependencies=[ManageOnly])
async def assign_fee_plan(student_id: str, payload: FeePlanAssign, db: DbDep):
    """(Re)build a student's fee plan from the class structure plus extra items."""
    student = await get_student_or_404(db, student_id)

    components: list[dict] = []
    academic_year = payload.academic_year or settings.academic_year

    if payload.use_classroom_structure and student.get("classroom_id"):
        classroom = await db.classrooms.find_one(
            {"_id": to_object_id(student["classroom_id"], "classroom id")}
        )
        if classroom:
            components.extend(classroom.get("fee_components") or [])
            academic_year = (
                payload.academic_year
                or classroom.get("academic_year")
                or settings.academic_year
            )

    components.extend(c.model_dump() for c in payload.extra_items)
    if not components and payload.agreed_fee is None:
        raise HTTPException(
            status_code=400,
            detail="No fee components found. Add a fee structure to the class, "
                   "provide extra items, or set an agreed fee.",
        )

    plan = build_fee_plan(
        components,
        academic_year=academic_year,
        agreed_total=payload.agreed_fee,
        discount=payload.discount,
        discount_reason=payload.discount_reason,
    )
    doc = await db.students.find_one_and_update(
        {"_id": student["_id"]},
        {"$set": {"fee_plan": encode_dates(plan), "updated_at": now_utc()}},
        return_document=True,
    )
    return await enrich(db, doc)
