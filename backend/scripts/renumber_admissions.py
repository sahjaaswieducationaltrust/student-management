"""Re-prefix admission numbers already issued, e.g. ADM20260002 -> HKB20260002.

Changing ADMISSION_PREFIX only affects *new* admissions — numbers already in the
register are never rewritten automatically, because an admission number may be
printed on a receipt a parent is holding. This script does the rewrite
deliberately, when you have decided that is what you want.

Receipts carry a denormalised copy of the admission number, so those are updated
in the same pass; otherwise old receipts would keep showing the old number and
the fee search by admission number would miss them.

Runs as a dry run unless you pass --apply:

    backend\\.venv\\Scripts\\python.exe backend/scripts/renumber_admissions.py
    backend\\.venv\\Scripts\\python.exe backend/scripts/renumber_admissions.py --apply

Options:
    --from PREFIX   prefix to replace (default: ADM)
    --to PREFIX     replacement (default: ADMISSION_PREFIX from the environment)
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo import MongoClient

from app.config import settings  # noqa: E402  (needs the sys.path line above)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="old", default="ADM", help="prefix to replace")
    parser.add_argument("--to", dest="new", default=settings.admission_prefix)
    parser.add_argument("--apply", action="store_true", help="write the changes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    old, new = args.old.strip(), args.new.strip()

    if not old or not new:
        print("Both --from and --to must be non-empty.")
        return 2
    if old == new:
        print(f"--from and --to are both {old!r}. Nothing to do.")
        return 0

    client = MongoClient(settings.mongodb_uri)
    db = client[settings.mongodb_db]

    # Anchored so a prefix can never match in the middle of a number.
    pattern = re.compile(f"^{re.escape(old)}")
    students = list(
        db.students.find({"admission_no": {"$regex": f"^{re.escape(old)}"}},
                         {"admission_no": 1, "first_name": 1, "last_name": 1})
    )

    if not students:
        print(f"No admission numbers start with {old!r}. Nothing to do.")
        return 0

    print(f"{'Applying' if args.apply else 'Dry run —'} {len(students)} student(s):\n")
    receipts_total = 0

    for student in students:
        current = student["admission_no"]
        replacement = pattern.sub(new, current)
        name = " ".join(filter(None, [student.get("first_name"), student.get("last_name")]))

        clash = db.students.find_one(
            {"admission_no": replacement, "_id": {"$ne": student["_id"]}}, {"_id": 1}
        )
        if clash:
            print(f"  SKIP  {current} -> {replacement}  ({name}) — that number is already taken")
            continue

        receipts = db.payments.count_documents({"admission_no": current})
        receipts_total += receipts
        print(f"  {current} -> {replacement}  ({name}, {receipts} receipt(s))")

        if args.apply:
            db.students.update_one(
                {"_id": student["_id"]}, {"$set": {"admission_no": replacement}}
            )
            if receipts:
                db.payments.update_many(
                    {"admission_no": current}, {"$set": {"admission_no": replacement}}
                )

    if args.apply:
        print(f"\nDone. {len(students)} student(s) and {receipts_total} receipt(s) updated.")
    else:
        print(f"\nNothing was written. Re-run with --apply to update "
              f"{len(students)} student(s) and {receipts_total} receipt(s).")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
