from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends

from ..config import settings
from ..deps import DbDep, get_current_user
from ..schemas import DashboardStats
from ..utils import encode_dates, money, person_name, serialize

router = APIRouter(prefix="/api", tags=["dashboard"], dependencies=[Depends(get_current_user)])


@router.get("/settings")
async def school_settings():
    """Branding used by the UI header and the on-screen receipt."""
    return {
        "school_name": settings.school_name,
        "school_branch": settings.school_branch,
        "school_full_name": settings.school_full_name,
        "school_trust": settings.school_trust,
        "school_legal_line": settings.school_legal_line,
        "school_tagline": settings.school_tagline,
        "school_address": settings.school_address,
        "school_phone": settings.school_phone,
        "school_email": settings.school_email,
        "school_website": settings.school_website,
        "currency_symbol": settings.currency_symbol,
        "academic_year": settings.academic_year,
    }


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(db: DbDep):
    today = date.today()
    month_start = datetime(today.year, today.month, 1, tzinfo=timezone.utc)
    day_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    day_end = datetime.combine(today, time.max, tzinfo=timezone.utc)

    students_total = await db.students.count_documents({})
    students_active = await db.students.count_documents({"status": "active"})
    teachers_active = await db.teachers.count_documents({"status": "active"})
    classrooms_count = await db.classrooms.count_documents({})

    # ---- fee position across active students ----
    paid_cursor = await db.payments.aggregate(
        [
            {"$match": {"cancelled": {"$ne": True}}},
            {"$group": {"_id": "$student_id", "total": {"$sum": "$amount"}}},
        ]
    )
    paid_map = {r["_id"]: money(r["total"]) for r in await paid_cursor.to_list(5000)}

    active = await db.students.find(
        {"status": "active"}, {"fee_plan.net_payable": 1}
    ).to_list(5000)
    expected = 0.0
    outstanding = 0.0
    for student in active:
        net = money((student.get("fee_plan") or {}).get("net_payable", 0))
        expected += net
        outstanding += max(0.0, net - paid_map.get(str(student["_id"]), 0.0))

    collected_cursor = await db.payments.aggregate(
        [
            {"$match": {"cancelled": {"$ne": True}}},
            {
                "$group": {
                    "_id": None,
                    "all": {"$sum": "$amount"},
                    "this_month": {
                        "$sum": {
                            "$cond": [{"$gte": ["$paid_on", month_start]}, "$amount", 0]
                        }
                    },
                    "today": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$gte": ["$paid_on", day_start]},
                                        {"$lte": ["$paid_on", day_end]},
                                    ]
                                },
                                "$amount",
                                0,
                            ]
                        }
                    },
                }
            },
        ]
    )
    totals = await collected_cursor.to_list(1)
    collected = totals[0] if totals else {"all": 0, "this_month": 0, "today": 0}

    # ---- students per class ----
    class_docs = await db.classrooms.find({}, {"name": 1}).sort("name", 1).to_list(200)
    by_class_cursor = await db.students.aggregate(
        [
            {"$match": {"status": "active"}},
            {"$group": {"_id": "$classroom_id", "count": {"$sum": 1}}},
        ]
    )
    counts = {r["_id"]: r["count"] for r in await by_class_cursor.to_list(200)}
    students_by_class = [
        {"name": c["name"], "count": counts.get(str(c["_id"]), 0)} for c in class_docs
    ]
    if counts.get(None):
        students_by_class.append({"name": "Unassigned", "count": counts[None]})

    # ---- 6-month collection trend ----
    trend_cursor = await db.payments.aggregate(
        [
            {"$match": {"cancelled": {"$ne": True}}},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m", "date": "$paid_on"}},
                    "amount": {"$sum": "$amount"},
                }
            },
            {"$sort": {"_id": -1}},
            {"$limit": 6},
        ]
    )
    trend = [
        {"month": r["_id"], "amount": money(r["amount"])}
        for r in reversed(await trend_cursor.to_list(6))
    ]

    # ---- attendance today ----
    attendance_today = await db.attendance.count_documents({"date": encode_dates(today)})
    present_today = await db.attendance.count_documents(
        {"date": encode_dates(today), "status": {"$in": ["present", "late"]}}
    )

    recent_payments = (
        await db.payments.find({}).sort("paid_on", -1).to_list(5)
    )
    recent_students = (
        await db.students.find({}, {"first_name": 1, "last_name": 1, "admission_no": 1,
                                    "admission_date": 1, "classroom_id": 1})
        .sort("created_at", -1)
        .to_list(5)
    )
    class_names = {str(c["_id"]): c["name"] for c in class_docs}

    return {
        "students_total": students_total,
        "students_active": students_active,
        "teachers_active": teachers_active,
        "classrooms": classrooms_count,
        "fees_expected": money(expected),
        "fees_collected": money(collected.get("all", 0)),
        "fees_outstanding": money(outstanding),
        "collected_this_month": money(collected.get("this_month", 0)),
        "collected_today": money(collected.get("today", 0)),
        "attendance_today_present": present_today,
        "attendance_today_marked": attendance_today,
        "students_by_class": students_by_class,
        "collection_trend": trend,
        "recent_payments": [serialize(p) for p in recent_payments],
        "recent_admissions": [
            {
                "id": str(s["_id"]),
                "name": person_name(s.get("first_name"), s.get("last_name")),
                "admission_no": s.get("admission_no"),
                "admission_date": s.get("admission_date"),
                "classroom_name": class_names.get(s.get("classroom_id") or ""),
            }
            for s in recent_students
        ],
    }
