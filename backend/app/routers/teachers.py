import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from ..deps import DbDep, get_current_user, require_roles
from ..schemas import TeacherCreate, TeacherOut, TeacherUpdate
from ..services.counters import next_employee_no
from ..utils import encode_dates, name_sort_key, now_utc, serialize, to_object_id

router = APIRouter(
    prefix="/api/teachers", tags=["teachers"], dependencies=[Depends(get_current_user)]
)

ManageOnly = Depends(require_roles("admin", "staff"))


async def enrich(db: AsyncDatabase, doc: dict) -> dict:
    out = serialize(doc)
    out["full_name"] = " ".join(filter(None, [out.get("first_name"), out.get("last_name")]))
    classes = await db.classrooms.find({"class_teacher_id": out["id"]}, {"name": 1}).to_list(50)
    out["classrooms"] = [c["name"] for c in classes]
    return out


@router.get("", response_model=list[TeacherOut])
async def list_teachers(
    db: DbDep,
    search: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
):
    query: dict = {}
    if status_filter:
        query["status"] = status_filter
    if search:
        rx = re.compile(re.escape(search.strip()), re.IGNORECASE)
        query["$or"] = [
            {"first_name": rx},
            {"last_name": rx},
            {"employee_no": rx},
            {"phone": rx},
            {"designation": rx},
        ]
    docs = sorted(await db.teachers.find(query).to_list(500), key=name_sort_key)
    return [await enrich(db, d) for d in docs]


@router.post("", response_model=TeacherOut, status_code=status.HTTP_201_CREATED,
             dependencies=[ManageOnly])
async def create_teacher(payload: TeacherCreate, db: DbDep):
    doc = encode_dates(payload.model_dump(exclude={"employee_no"}))
    doc["employee_no"] = payload.employee_no or await next_employee_no(db)
    doc["created_at"] = now_utc()
    try:
        result = await db.teachers.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Employee number {doc['employee_no']} already exists",
        )
    doc["_id"] = result.inserted_id
    return await enrich(db, doc)


@router.get("/{teacher_id}", response_model=TeacherOut)
async def get_teacher(teacher_id: str, db: DbDep):
    doc = await db.teachers.find_one({"_id": to_object_id(teacher_id, "teacher id")})
    if doc is None:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return await enrich(db, doc)


@router.patch("/{teacher_id}", response_model=TeacherOut, dependencies=[ManageOnly])
async def update_teacher(teacher_id: str, payload: TeacherUpdate, db: DbDep):
    updates = encode_dates(payload.model_dump(exclude_none=True))
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    updates["updated_at"] = now_utc()
    doc = await db.teachers.find_one_and_update(
        {"_id": to_object_id(teacher_id, "teacher id")},
        {"$set": updates},
        return_document=True,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return await enrich(db, doc)


@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_roles("admin"))])
async def delete_teacher(teacher_id: str, db: DbDep):
    result = await db.teachers.delete_one({"_id": to_object_id(teacher_id, "teacher id")})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Teacher not found")
    # Detach from any class they were leading.
    await db.classrooms.update_many(
        {"class_teacher_id": teacher_id}, {"$set": {"class_teacher_id": None}}
    )
