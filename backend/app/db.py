from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from .config import settings


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
    await db.classrooms.create_index("name")
    await db.payments.create_index("receipt_no", unique=True)
    await db.payments.create_index([("student_id", 1), ("paid_on", -1)])
    await db.payments.create_index("paid_on")
    await db.attendance.create_index(
        [("student_id", 1), ("date", 1)], unique=True
    )
    await db.attendance.create_index([("date", 1), ("classroom_id", 1)])
