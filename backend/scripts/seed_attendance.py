"""Fill the attendance register with sample marks, for demos and screenshots.

Only the attendance collection is touched — children, receipts, users and
counters are left exactly as they are. This is deliberately not the `--reset`
seeder: that one rebuilds the whole database from scratch and would delete
real enrolments.

Marks written here carry ``generated: True``. That flag is what makes the run
reversible: --clear removes only these rows, and a real mark saved from the
Attendance page is never overwritten, so a day the staff actually recorded
survives a re-run.

Runs as a dry run unless you pass --apply:

    backend\\.venv\\Scripts\\python.exe backend/scripts/seed_attendance.py
    backend\\.venv\\Scripts\\python.exe backend/scripts/seed_attendance.py --apply
    backend\\.venv\\Scripts\\python.exe backend/scripts/seed_attendance.py --clear --apply
"""

import argparse
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo import MongoClient, UpdateOne

from app.config import settings  # noqa: E402  (needs the sys.path line above)

MARKED_BY = "Sample data"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=14,
                        help="how many weekdays back to fill, ending today (default 14)")
    parser.add_argument("--present", type=int, default=88,
                        help="percentage marked present; the rest split absent/late (default 88)")
    parser.add_argument("--classroom", help="limit to one classroom name, e.g. UKG")
    parser.add_argument("--seed", type=int, default=20260810,
                        help="random seed, so repeat runs produce the same register")
    parser.add_argument("--clear", action="store_true",
                        help="remove generated marks instead of adding them")
    parser.add_argument("--apply", action="store_true", help="write the changes")
    return parser.parse_args()


def weekdays_ending_today(count: int) -> list[date]:
    """The last ``count`` weekdays, oldest first. Weekends carry no roll call."""
    days: list[date] = []
    day = date.today()
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return sorted(days)


def as_stored(value: date) -> datetime:
    """Match how the app stores a date: midnight UTC (see utils.encode_dates)."""
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def main() -> int:
    args = parse_args()
    if not 0 <= args.present <= 100:
        print("--present must be between 0 and 100.")
        return 2

    client = MongoClient(settings.mongodb_uri)
    db = client[settings.mongodb_db]

    if args.clear:
        count = db.attendance.count_documents({"generated": True})
        real = db.attendance.count_documents({"generated": {"$ne": True}})
        if args.apply:
            db.attendance.delete_many({"generated": True})
            print(f"Removed {count} generated mark(s). {real} real mark(s) left untouched.")
        else:
            print(f"Would remove {count} generated mark(s). "
                  f"{real} real mark(s) would be left untouched.")
            print("Re-run with --apply to remove them.")
        client.close()
        return 0

    class_names = {str(c["_id"]): c["name"] for c in db.classrooms.find({}, {"name": 1})}
    query: dict = {"status": "active"}
    if args.classroom:
        matches = [cid for cid, name in class_names.items()
                   if name.lower() == args.classroom.lower()]
        if not matches:
            print(f"No classroom named {args.classroom!r}. "
                  f"Known: {sorted(class_names.values())}")
            client.close()
            return 2
        query["classroom_id"] = matches[0]

    students = list(db.students.find(query, {"first_name": 1, "last_name": 1, "classroom_id": 1}))
    if not students:
        print("No active children match. Enrol a child first, or drop --classroom.")
        client.close()
        return 0

    days = weekdays_ending_today(args.days)
    # Seeded so a dry run and the --apply that follows agree, and so re-running
    # does not reshuffle a register someone has already looked at.
    rng = random.Random(args.seed)
    absent = (100 - args.present) * 2 // 3
    weights = [args.present, absent, 100 - args.present - absent]

    operations: list[UpdateOne] = []
    tally = {"present": 0, "absent": 0, "late": 0}
    protected = 0

    for day in days:
        stored = as_stored(day)
        for student in students:
            sid = str(student["_id"])
            existing = db.attendance.find_one(
                {"student_id": sid, "date": stored}, {"generated": 1}
            )
            if existing and not existing.get("generated"):
                protected += 1  # a real roll call — never overwrite it
                continue
            status = rng.choices(["present", "absent", "late"], weights=weights)[0]
            tally[status] += 1
            operations.append(
                UpdateOne(
                    {"student_id": sid, "date": stored},
                    {
                        "$set": {
                            "classroom_id": student.get("classroom_id"),
                            "status": status,
                            "remarks": None,
                            "marked_by": MARKED_BY,
                            "generated": True,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                    upsert=True,
                )
            )

    child_names = ", ".join(
        " ".join(filter(None, [s.get("first_name"), s.get("last_name")])) for s in students[:4]
    )
    if len(students) > 4:
        child_names += f", +{len(students) - 4} more"

    print(f"{'Applying' if args.apply else 'Dry run —'} sample attendance\n")
    print(f"  children : {len(students)}  ({child_names})")
    print(f"  weekdays : {len(days)}  ({days[0]} to {days[-1]})")
    print(f"  marks    : {len(operations)}")
    print(f"             present {tally['present']}, absent {tally['absent']}, late {tally['late']}")
    if protected:
        print(f"  skipped  : {protected} real mark(s) already recorded by staff")

    if args.apply and operations:
        result = db.attendance.bulk_write(operations, ordered=False)
        print(f"\nDone. {result.upserted_count} created, {result.modified_count} updated.")
        print("Remove them again with:  --clear --apply")
    elif not args.apply:
        print("\nNothing was written. Re-run with --apply.")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
