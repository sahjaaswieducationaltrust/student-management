from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import UpdateOne

from ..deps import CurrentUser, DbDep, get_current_user
from ..schemas import AttendanceBulkCreate, AttendanceOut
from ..utils import encode_dates, name_sort_key, now_utc, person_name, to_object_id

router = APIRouter(
    prefix="/api/attendance", tags=["attendance"], dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=list[AttendanceOut])
async def attendance_sheet(
    db: DbDep,
    classroom_id: str | None = None,
    session: Literal["class", "daycare"] = "class",
    on: date | None = Query(default=None, alias="date"),
):
    """Roll-call sheet plus any mark already saved.

    The daycare roll is drawn from who is *enrolled in daycare*, not from a
    class, because daycare cuts across classes: a Nursery child staying three
    hours belongs on both rolls, and a child from another school belongs only
    on this one.
    """
    on = on or date.today()

    if session == "daycare":
        query: dict = {"status": "active", "daycare.enrolled": True}
        if classroom_id:
            query["classroom_id"] = classroom_id
    else:
        if not classroom_id:
            raise HTTPException(
                status_code=400, detail="classroom_id is required for the class roll"
            )
        query = {"status": "active", "classroom_id": classroom_id}

    students = sorted(await db.students.find(query).to_list(300), key=name_sort_key)

    marks = await db.attendance.find({
        "date": encode_dates(on),
        "session": session,
        "student_id": {"$in": [str(s["_id"]) for s in students]},
    }).to_list(300)
    by_student = {m["student_id"]: m for m in marks}

    rows = []
    for student in students:
        sid = str(student["_id"])
        mark = by_student.get(sid)
        daycare = student.get("daycare") or {}
        rows.append(
            {
                "id": str(mark["_id"]) if mark else None,
                "student_id": sid,
                "student_name": person_name(student.get("first_name"), student.get("last_name")),
                "gender": student.get("gender"),
                "admission_no": student.get("admission_no", ""),
                "classroom_id": student.get("classroom_id"),
                "session": session,
                "daycare_hours": daycare.get("hours_per_day") if daycare.get("enrolled") else None,
                "date": on,
                "status": mark.get("status") if mark else None,
                "remarks": mark.get("remarks") if mark else None,
            }
        )
    return rows


@router.post("", status_code=status.HTTP_200_OK)
async def save_attendance(payload: AttendanceBulkCreate, db: DbDep, user: CurrentUser):
    if not payload.entries:
        raise HTTPException(status_code=400, detail="No entries supplied")

    on = encode_dates(payload.date)
    operations = [
        UpdateOne(
            {"student_id": entry.student_id, "date": on, "session": payload.session},
            {
                "$set": {
                    "classroom_id": payload.classroom_id,
                    "status": entry.status.value,
                    "remarks": entry.remarks,
                    "marked_by": user.get("name"),
                    "updated_at": now_utc(),
                }
            },
            upsert=True,
        )
        for entry in payload.entries
    ]
    result = await db.attendance.bulk_write(operations, ordered=False)
    return {
        "saved": len(operations),
        "created": result.upserted_count,
        "updated": result.modified_count,
    }


@router.get("/student/{student_id}")
async def student_attendance(
    student_id: str,
    db: DbDep,
    days: int = Query(default=30, ge=1, le=365),
):
    since = encode_dates(date.today() - timedelta(days=days))
    docs = (
        await db.attendance.find({"student_id": student_id, "date": {"$gte": since}})
        .sort("date", -1)
        .to_list(400)
    )
    counts = {"present": 0, "absent": 0, "late": 0, "holiday": 0}
    for doc in docs:
        counts[doc.get("status", "present")] = counts.get(doc.get("status", "present"), 0) + 1

    working_days = counts["present"] + counts["absent"] + counts["late"]
    return {
        "student_id": student_id,
        "days": days,
        "counts": counts,
        "working_days": working_days,
        "percentage": round(
            ((counts["present"] + counts["late"]) / working_days * 100) if working_days else 0, 1
        ),
        "records": [
            {
                "date": d["date"],
                "status": d.get("status"),
                "remarks": d.get("remarks"),
            }
            for d in docs
        ],
    }


@router.get("/summary")
async def attendance_summary(db: DbDep, on: date | None = Query(default=None, alias="date")):
    """Per-class present/absent counts for a single day."""
    on = encode_dates(on or date.today())
    cursor = await db.attendance.aggregate(
        [
            {"$match": {"date": on}},
            {
                "$group": {
                    "_id": {"classroom_id": "$classroom_id", "status": "$status"},
                    "count": {"$sum": 1},
                }
            },
        ]
    )
    rows = await cursor.to_list(500)
    classrooms = await db.classrooms.find({}, {"name": 1}).to_list(200)
    names = {str(c["_id"]): c["name"] for c in classrooms}

    grouped: dict[str, dict] = {}
    for row in rows:
        cid = row["_id"].get("classroom_id") or ""
        entry = grouped.setdefault(
            cid,
            {
                "classroom_id": cid,
                "classroom_name": names.get(cid, "Unassigned"),
                "present": 0,
                "absent": 0,
                "late": 0,
                "holiday": 0,
            },
        )
        entry[row["_id"].get("status", "present")] = row["count"]
    return list(grouped.values())


@router.delete("/{attendance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attendance(attendance_id: str, db: DbDep):
    result = await db.attendance.delete_one(
        {"_id": to_object_id(attendance_id, "attendance id")}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Attendance record not found")
