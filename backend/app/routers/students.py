import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from ..config import settings
from ..deps import CurrentUser, DbDep, get_current_user, require_roles
from ..schemas import (
    FEE_CATEGORY_LABELS,
    FeeCategory,
    FeePlanAssign,
    StudentCreate,
    StudentCreatedOut,
    StudentListResponse,
    StudentOut,
    StudentUpdate,
    is_free_category,
)
from ..services.counters import next_admission_no
from ..services.daycare import build_enrolment, eligibility_note, fee_component
from ..services.fees import build_fee_plan, summarise
from ..services.payments import create_payment, paid_totals
from ..utils import (
    age_from_dob,
    encode_dates,
    money,
    name_sort_key,
    now_utc,
    person_name,
    serialize,
    title_name,
    to_object_id,
)

router = APIRouter(
    prefix="/api/students", tags=["students"], dependencies=[Depends(get_current_user)]
)

ManageOnly = Depends(require_roles("admin", "staff"))


def fee_summary(fee_plan: dict | None, paid: float, next_due_override=None) -> dict:
    """Compact fee position for list views — total, paid, balance, next due."""
    summary = summarise(fee_plan, paid, next_due_override)
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
    # Proper-cased on the way out as well as on the way in, so records created
    # before the normalisation existed still read correctly.
    out["first_name"] = title_name(out.get("first_name"))
    out["last_name"] = title_name(out.get("last_name")) or None
    out["full_name"] = person_name(out.get("first_name"), out.get("last_name"))
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
    out["fee_summary"] = fee_summary(
        doc.get("fee_plan"), paid, doc.get("next_due_override")
    )
    out["fee_category_label"] = FEE_CATEGORY_LABELS.get(
        out.get("fee_category") or FeeCategory.regular.value, "Regular"
    )
    out["daycare_eligibility_note"] = eligibility_note(doc.get("daycare"), doc.get("date_of_birth"))
    return out


async def _rebuild_plan(db: AsyncDatabase, student: dict, daycare: dict | None) -> dict:
    """Regenerate a plan from the class structure plus the daycare add-on.

    Any concession already agreed is carried over, so re-pricing daycare does
    not quietly undo a discount the parents were promised.
    """
    plan = student.get("fee_plan") or {}
    components: list[dict] = []
    academic_year = plan.get("academic_year") or settings.academic_year

    if student.get("classroom_id"):
        classroom = await db.classrooms.find_one(
            {"_id": to_object_id(student["classroom_id"], "classroom id")}
        )
        if classroom:
            components.extend(classroom.get("fee_components") or [])
            academic_year = classroom.get("academic_year") or academic_year

    components.extend(fee_component(daycare))

    # An agreed total was negotiated against the old set of components, so it
    # cannot simply carry over — the daycare change has to move the total.
    # A percentage concession is preserved instead.
    discount = money(plan.get("discount", 0))
    gross_before = money(plan.get("gross", 0))
    share = (discount / gross_before) if gross_before > 0 else 0.0

    rebuilt = build_fee_plan(
        components,
        academic_year=academic_year,
        discount_reason=plan.get("discount_reason"),
    )
    if share > 0:
        rebuilt = build_fee_plan(
            components,
            academic_year=academic_year,
            discount=money(rebuilt["gross"] * share),
            discount_reason=plan.get("discount_reason"),
        )
    return rebuilt


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
    # Sorted here rather than in the query: the rows get filtered and paged in
    # Python below anyway, and a case-folded key is not something Mongo's
    # default byte ordering gives us.
    docs = sorted(await db.students.find(query).to_list(2000), key=name_sort_key)
    paid_map = await paid_totals(db, [str(d["_id"]) for d in docs])

    rows = []
    for doc in docs:
        summary = fee_summary(
            doc.get("fee_plan"),
            paid_map.get(str(doc["_id"]), 0.0),
            doc.get("next_due_override"),
        )
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
    doc["first_name"] = title_name(doc.get("first_name"))
    doc["last_name"] = title_name(doc.get("last_name")) or None
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

    # Daycare is an add-on rather than a class, so it is priced from the child's
    # own hours and age and appended to whatever the class charges. A child
    # taking only daycare gets a plan made of this line alone.
    doc["daycare"] = encode_dates(
        build_enrolment(
            hours_per_day=payload.daycare.hours_per_day if payload.daycare else 0,
            dob=payload.date_of_birth,
            rate_per_hour=payload.daycare.rate_per_hour if payload.daycare else None,
            started_on=(payload.daycare.started_on if payload.daycare else None)
            or payload.admission_date,
            note=payload.daycare.note if payload.daycare else None,
        )
    )
    components = [*components, *fee_component(doc["daycare"])]

    # A concession category is a full waiver and overrides whatever fee was
    # typed in, so a mis-keyed amount can never make a free seat billable.
    free_seat = is_free_category(doc.get("fee_category"))
    agreed_fee = 0.0 if free_seat else payload.agreed_fee
    fee_note = payload.fee_note
    if free_seat:
        label = FEE_CATEGORY_LABELS[doc["fee_category"]]
        fee_note = f"{label} — no fee" + (f" ({payload.fee_note})" if payload.fee_note else "")

    if components or agreed_fee is not None:
        doc["fee_plan"] = encode_dates(
            build_fee_plan(
                components,
                academic_year=academic_year,
                agreed_total=agreed_fee,
                discount_reason=fee_note,
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
            particulars=initial.particulars,
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
    for field in ("first_name", "last_name"):
        if field in updates:
            updates[field] = title_name(updates[field]) or None
    if updates.get("classroom_id"):
        exists = await db.classrooms.count_documents(
            {"_id": to_object_id(updates["classroom_id"], "classroom id")}
        )
        if not exists:
            raise HTTPException(status_code=400, detail="Classroom not found")
    updates["updated_at"] = now_utc()

    existing = await get_student_or_404(db, student_id)

    # Changing the hours changes the money, so the plan is rebuilt here rather
    # than left for someone to remember to regenerate from the profile.
    if "daycare" in updates:
        updates["daycare"] = encode_dates(
            build_enrolment(
                hours_per_day=updates["daycare"].get("hours_per_day", 0),
                dob=updates.get("date_of_birth") or existing.get("date_of_birth"),
                rate_per_hour=updates["daycare"].get("rate_per_hour"),
                started_on=updates["daycare"].get("started_on"),
                note=updates["daycare"].get("note"),
            )
        )
        if not is_free_category(
            updates.get("fee_category") or existing.get("fee_category")
        ):
            updates["fee_plan"] = encode_dates(
                await _rebuild_plan(db, existing, updates["daycare"])
            )

    # Moving a child onto a concession category has to zero the money as well as
    # the label, otherwise a staff ward keeps showing up in the dues list.
    if is_free_category(updates.get("fee_category")):
        plan = existing.get("fee_plan") or {}
        label = FEE_CATEGORY_LABELS[updates["fee_category"]]
        updates["fee_plan"] = encode_dates(
            build_fee_plan(
                plan.get("items") or [],
                academic_year=plan.get("academic_year") or settings.academic_year,
                agreed_total=0.0,
                discount_reason=f"{label} — no fee",
            )
        )

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
    # Rebuilding the plan must not quietly drop the daycare the child is
    # enrolled in — it is priced on the student, not the classroom, so nothing
    # else would put it back.
    components.extend(fee_component(student.get("daycare")))

    # The category on the payload wins; falling back to the one already on the
    # record means rebuilding a free seat's plan cannot silently start charging.
    category = (
        payload.fee_category.value
        if payload.fee_category is not None
        else student.get("fee_category")
    )
    free_seat = is_free_category(category)

    if not components and payload.agreed_fee is None and not free_seat:
        raise HTTPException(
            status_code=400,
            detail="No fee components found. Add a fee structure to the class, "
                   "provide extra items, or set an agreed fee.",
        )

    reason = payload.discount_reason
    if free_seat:
        label = FEE_CATEGORY_LABELS[category]
        reason = f"{label} — no fee" + (f" ({reason})" if reason else "")

    plan = build_fee_plan(
        components,
        academic_year=academic_year,
        agreed_total=0.0 if free_seat else payload.agreed_fee,
        discount=0 if free_seat else payload.discount,
        discount_reason=reason,
    )
    updates: dict = {"fee_plan": encode_dates(plan), "updated_at": now_utc()}
    if payload.fee_category is not None:
        updates["fee_category"] = payload.fee_category.value

    doc = await db.students.find_one_and_update(
        {"_id": student["_id"]},
        {"$set": updates},
        return_document=True,
    )
    return await enrich(db, doc)
