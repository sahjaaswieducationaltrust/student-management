"""Atomic, gap-free sequence numbers for admission numbers and receipt numbers."""

from datetime import date

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from ..config import settings


async def next_sequence(db: AsyncDatabase, key: str) -> int:
    doc = await db.counters.find_one_and_update(
        {"_id": key},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["value"])


async def next_admission_no(db: AsyncDatabase) -> str:
    year = date.today().year
    seq = await next_sequence(db, f"admission:{year}")
    return f"{settings.admission_prefix}{year}{seq:04d}"


async def next_employee_no(db: AsyncDatabase) -> str:
    year = date.today().year
    seq = await next_sequence(db, f"employee:{year}")
    return f"{settings.employee_prefix}{year}{seq:03d}"


async def next_receipt_no(db: AsyncDatabase, academic_year: str | None = None) -> str:
    ay = academic_year or settings.academic_year
    seq = await next_sequence(db, f"receipt:{ay}")
    return f"RCP/{ay}/{seq:05d}"
