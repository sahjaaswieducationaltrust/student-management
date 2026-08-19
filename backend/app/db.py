import logging

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from .config import settings

log = logging.getLogger("preschool.db")


class _Mongo:
    client: AsyncMongoClient | None = None
    db: AsyncDatabase | None = None


mongo = _Mongo()


def get_db() -> AsyncDatabase:
    if mongo.db is None:
        raise RuntimeError("Database is not initialised yet")
    return mongo.db


async def connect_to_mongo() -> None:
    mongo.client = AsyncMongoClient(settings.mongodb_uri, tz_aware=True)
    mongo.db = mongo.client[settings.mongodb_db]
    await mongo.client.admin.command("ping")
    await _ensure_indexes(mongo.db)


async def close_mongo_connection() -> None:
    if mongo.client is not None:
        await mongo.client.close()
        mongo.client = None
        mongo.db = None


async def _ensure_indexes(db: AsyncDatabase) -> None:
    await db.users.create_index("email", unique=True)
    await db.students.create_index("admission_no", unique=True)
    await db.students.create_index([("status", 1), ("classroom_id", 1)])
    await db.students.create_index([("first_name", "text"), ("last_name", "text")])
    await db.teachers.create_index("employee_no", unique=True)
    await db.staff.create_index("employee_no", unique=True)
    await db.staff.create_index([("status", 1), ("department", 1)])
    await db.classrooms.create_index("name")
    await db.payments.create_index("receipt_no", unique=True)
    await db.payments.create_index([("student_id", 1), ("paid_on", -1)])
    await db.payments.create_index("paid_on")
    await _migrate_attendance_sessions(db)
    # One mark per child per day *per session*: a child in Nursery who also
    # stays for daycare is marked twice, and the old two-key index made the
    # second mark overwrite the first.
    await db.attendance.create_index(
        [("student_id", 1), ("date", 1), ("session", 1)], unique=True
    )
    await db.attendance.create_index([("date", 1), ("classroom_id", 1)])


async def _migrate_attendance_sessions(db: AsyncDatabase) -> None:
    """Give existing marks a session and retire the old two-key unique index.

    Runs on every start and does nothing after the first: the backfill matches
    no documents once they all carry a session, and the index drop is skipped
    when it is already gone. Doing it here rather than in a script means a
    deploy cannot land the new code against an index that would reject it.
    """
    result = await db.attendance.update_many(
        {"session": {"$exists": False}}, {"$set": {"session": "class"}}
    )
    if result.modified_count:
        log.info("Backfilled %d attendance record(s) with session=class",
                 result.modified_count)

    existing = await db.attendance.index_information()
    for name, spec in existing.items():
        keys = [k for k, _ in spec.get("key", [])]
        if keys == ["student_id", "date"] and spec.get("unique"):
            await db.attendance.drop_index(name)
            log.info("Dropped the old attendance index %r — replaced by a "
                     "per-session one", name)
