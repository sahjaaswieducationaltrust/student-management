"""Create the collections, indexes and the first admin account.

    python -m app.init_db

Safe to re-run — creating an existing index or admin is a no-op. The API does
this automatically on startup too; this command is for setting the database up
without starting the server.
"""

import asyncio
import sys

from .config import settings
from .db import close_mongo_connection, connect_to_mongo, get_db
from .main import bootstrap_admin
from .utils import now_utc

# The standard preschool programmes. Created empty (no fee components) so the
# class dropdown is usable immediately — set each class's fees under
# "Classes & Fees" in the app.
DEFAULT_CLASSES = [
    {"name": "Daycare", "level": "Daycare", "capacity": 25},
    {"name": "Playgroup", "level": "Playgroup", "capacity": 20},
    {"name": "Nursery", "level": "Nursery", "capacity": 20},
    {"name": "LKG", "level": "LKG", "capacity": 25},
    {"name": "UKG", "level": "UKG", "capacity": 25},
]

COLLECTIONS = [
    ("users", "staff logins and roles"),
    ("classrooms", "classes and their fee structures"),
    ("students", "children, guardians, medical info, fee plans"),
    ("teachers", "teaching staff"),
    ("staff", "non-teaching staff"),
    ("payments", "fee receipts"),
    ("attendance", "daily roll call"),
    ("counters", "admission / employee / receipt number sequences"),
]


async def main() -> int:
    print(f"\nDatabase: {settings.mongodb_db}\n")

    # connect_to_mongo() creates every index, which creates the collections too.
    await connect_to_mongo()
    db = get_db()

    existing = set(await db.list_collection_names())
    for name, purpose in COLLECTIONS:
        if name not in existing:
            # `counters` has no index, so nothing has created it yet.
            await db.create_collection(name)
        cursor = await db[name].list_indexes()
        indexes = await cursor.to_list(None)
        print(f"  {name:<12} {len(indexes)} index(es)   {purpose}")

    print()
    await bootstrap_admin()

    # Standard classes, so the enrolment form's class dropdown is never empty.
    created = []
    for spec in DEFAULT_CLASSES:
        if await db.classrooms.count_documents({"name": spec["name"]}) == 0:
            await db.classrooms.insert_one(
                {
                    **spec,
                    "room": None,
                    "academic_year": settings.academic_year,
                    "class_teacher_id": None,
                    "fee_components": [],
                    "created_at": now_utc(),
                }
            )
            created.append(spec["name"])
    if created:
        print(f"\nCreated classes: {', '.join(created)}")
        print("  -> Set each class's fee structure under 'Classes & Fees' in the app.")

    users = await db.users.count_documents({})
    classes = await db.classrooms.count_documents({})
    print(f"\nDone. {len(COLLECTIONS)} collections ready, "
          f"{users} user account(s), {classes} class(es).")
    print(f"Sign in with {settings.admin_email} / {settings.admin_password}")
    print("Load demo data with:  python -m app.seed\n")

    await close_mongo_connection()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
