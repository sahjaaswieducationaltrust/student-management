import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from ..deps import DbDep, get_current_user, require_roles
from ..schemas import StaffCreate, StaffOut, StaffUpdate
from ..services.counters import next_employee_no
from ..utils import encode_dates, name_sort_key, now_utc, serialize, to_object_id

router = APIRouter(
    prefix="/api/staff", tags=["staff"], dependencies=[Depends(get_current_user)]
)

ManageOnly = Depends(require_roles("admin", "staff"))


def enrich(doc: dict) -> dict:
    out = serialize(doc)
    out["full_name"] = " ".join(filter(None, [out.get("first_name"), out.get("last_name")]))
    return out


@router.get("", response_model=list[StaffOut])
async def list_staff(
    db: DbDep,
    search: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    department: str | None = None,
):
    query: dict = {}
    if status_filter:
        query["status"] = status_filter
    if department:
        query["department"] = department
    if search:
        rx = re.compile(re.escape(search.strip()), re.IGNORECASE)
        query["$or"] = [
            {"first_name": rx},
            {"last_name": rx},
            {"employee_no": rx},
            {"phone": rx},
            {"designation": rx},
            {"department": rx},
        ]
    docs = sorted(await db.staff.find(query).to_list(500), key=name_sort_key)
    return [enrich(d) for d in docs]


@router.get("/departments", response_model=list[str])
async def list_departments(db: DbDep):
    """Departments already in use — fills the filter and the form's suggestions."""
    values = await db.staff.distinct("department")
    return sorted(v for v in values if v)


@router.post("", response_model=StaffOut, status_code=status.HTTP_201_CREATED,
             dependencies=[ManageOnly])
async def create_staff(payload: StaffCreate, db: DbDep):
    doc = encode_dates(payload.model_dump(exclude={"employee_no"}))
    doc["employee_no"] = payload.employee_no or await next_employee_no(db)
    doc["created_at"] = now_utc()
    try:
        result = await db.staff.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Employee number {doc['employee_no']} already exists",
        )
    doc["_id"] = result.inserted_id
    return enrich(doc)


@router.get("/{staff_id}", response_model=StaffOut)
async def get_staff(staff_id: str, db: DbDep):
    doc = await db.staff.find_one({"_id": to_object_id(staff_id, "staff id")})
    if doc is None:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return enrich(doc)


@router.patch("/{staff_id}", response_model=StaffOut, dependencies=[ManageOnly])
async def update_staff(staff_id: str, payload: StaffUpdate, db: DbDep):
    updates = encode_dates(payload.model_dump(exclude_none=True))
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    updates["updated_at"] = now_utc()
    doc = await db.staff.find_one_and_update(
        {"_id": to_object_id(staff_id, "staff id")},
        {"$set": updates},
        return_document=True,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return enrich(doc)


@router.delete("/{staff_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_roles("admin"))])
async def delete_staff(staff_id: str, db: DbDep):
    result = await db.staff.delete_one({"_id": to_object_id(staff_id, "staff id")})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Staff member not found")
