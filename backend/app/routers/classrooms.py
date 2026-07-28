from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase

from ..deps import DbDep, get_current_user, require_roles
from ..schemas import ClassroomCreate, ClassroomOut, ClassroomUpdate
from ..services.fees import OCCURRENCES
from ..utils import encode_dates, money, now_utc, serialize, to_object_id

router = APIRouter(
    prefix="/api/classrooms",
    tags=["classrooms"],
    dependencies=[Depends(get_current_user)],
)

ManageOnly = Depends(require_roles("admin", "staff"))


def annual_fee(components: list[dict]) -> float:
    return money(
        sum(
            money(c.get("amount")) * OCCURRENCES.get(c.get("frequency", "annual"), 1)
            for c in components or []
        )
    )


async def enrich(db: AsyncDatabase, doc: dict) -> dict:
    out = serialize(doc)
    out["student_count"] = await db.students.count_documents(
        {"classroom_id": out["id"], "status": "active"}
    )
    out["annual_fee"] = annual_fee(out.get("fee_components", []))
    out["class_teacher_name"] = None
    teacher_id = out.get("class_teacher_id")
    if teacher_id:
        teacher = await db.teachers.find_one({"_id": to_object_id(teacher_id, "teacher id")})
        if teacher:
            out["class_teacher_name"] = " ".join(
                filter(None, [teacher.get("first_name"), teacher.get("last_name")])
            )
    return out


@router.get("", response_model=list[ClassroomOut])
async def list_classrooms(db: DbDep, academic_year: str | None = None):
    query = {"academic_year": academic_year} if academic_year else {}
    docs = await db.classrooms.find(query).sort("name", 1).to_list(200)
    return [await enrich(db, d) for d in docs]


@router.post("", response_model=ClassroomOut, status_code=status.HTTP_201_CREATED,
             dependencies=[ManageOnly])
async def create_classroom(payload: ClassroomCreate, db: DbDep):
    doc = encode_dates(payload.model_dump())
    doc["created_at"] = now_utc()
    result = await db.classrooms.insert_one(doc)
    doc["_id"] = result.inserted_id
    return await enrich(db, doc)


@router.get("/{classroom_id}", response_model=ClassroomOut)
async def get_classroom(classroom_id: str, db: DbDep):
    doc = await db.classrooms.find_one({"_id": to_object_id(classroom_id, "classroom id")})
    if doc is None:
        raise HTTPException(status_code=404, detail="Classroom not found")
    return await enrich(db, doc)


@router.patch("/{classroom_id}", response_model=ClassroomOut, dependencies=[ManageOnly])
async def update_classroom(classroom_id: str, payload: ClassroomUpdate, db: DbDep):
    updates = encode_dates(payload.model_dump(exclude_none=True))
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    updates["updated_at"] = now_utc()
    doc = await db.classrooms.find_one_and_update(
        {"_id": to_object_id(classroom_id, "classroom id")},
        {"$set": updates},
        return_document=True,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Classroom not found")
    return await enrich(db, doc)


@router.delete("/{classroom_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[ManageOnly])
async def delete_classroom(classroom_id: str, db: DbDep):
    assigned = await db.students.count_documents({"classroom_id": classroom_id})
    if assigned:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{assigned} student(s) are still assigned to this class",
        )
    result = await db.classrooms.delete_one({"_id": to_object_id(classroom_id, "classroom id")})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Classroom not found")
