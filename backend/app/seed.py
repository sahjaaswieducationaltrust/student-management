"""Populate the database with realistic demo data.

    python -m app.seed          # add demo data (keeps existing records)
    python -m app.seed --reset  # wipe every collection first
"""

import asyncio
import random
import sys
from datetime import date, datetime, time, timedelta, timezone

from .config import settings
from .db import close_mongo_connection, connect_to_mongo, get_db
from .security import hash_password
from .services.counters import next_admission_no, next_employee_no, next_receipt_no
from .services.fees import auto_allocate_items, build_fee_plan
from .utils import encode_dates, money, now_utc

COLLECTIONS = [
    "users", "students", "teachers", "staff", "classrooms", "payments", "attendance",
    "counters",
]

CLASSES = [
    {
        "name": "Play Group A", "level": "Pre-Nursery / Play Group",
        "room": "Sunflower", "capacity": 15,
        "fee_components": [
            {"name": "Admission Fee", "amount": 8000, "frequency": "one_time"},
            {"name": "Tuition Fee", "amount": 3500, "frequency": "monthly"},
            {"name": "Activity Kit", "amount": 2500, "frequency": "term"},
        ],
    },
    {
        "name": "Nursery A", "level": "Nursery / Montessori-1",
        "room": "Rainbow", "capacity": 20,
        "fee_components": [
            {"name": "Admission Fee", "amount": 10000, "frequency": "one_time"},
            {"name": "Tuition Fee", "amount": 4200, "frequency": "monthly"},
            {"name": "Activity Kit", "amount": 3000, "frequency": "term"},
            {"name": "Annual Day & Excursions", "amount": 4000, "frequency": "annual"},
        ],
    },
    {
        "name": "LKG A", "level": "LKG / Montessori-2", "room": "Bluebell", "capacity": 22,
        "fee_components": [
            {"name": "Admission Fee", "amount": 12000, "frequency": "one_time"},
            {"name": "Tuition Fee", "amount": 5000, "frequency": "monthly"},
            {"name": "Books & Uniform", "amount": 6500, "frequency": "annual"},
            {"name": "Activity Kit", "amount": 3200, "frequency": "term"},
        ],
    },
    {
        "name": "UKG A", "level": "UKG / Montessori-3", "room": "Marigold", "capacity": 22,
        "fee_components": [
            {"name": "Admission Fee", "amount": 12000, "frequency": "one_time"},
            {"name": "Tuition Fee", "amount": 5500, "frequency": "monthly"},
            {"name": "Books & Uniform", "amount": 7000, "frequency": "annual"},
            {"name": "Activity Kit", "amount": 3500, "frequency": "term"},
        ],
    },
]

TEACHERS = [
    ("Meera", "Nair", "female", "Head Teacher", "M.A., B.Ed", 52000, ["Language", "Storytelling"]),
    ("Anjali", "Sharma", "female", "Class Teacher", "B.Ed, Montessori", 38000, ["Numeracy", "Art"]),
    ("Priya", "Reddy", "female", "Class Teacher", "B.A., NTT", 35000, ["Rhymes", "Craft"]),
    ("Rahul", "Verma", "male", "Activity Coach", "B.P.Ed", 30000, ["Physical Play", "Music"]),
    ("Fatima", "Khan", "female", "Assistant Teacher", "B.Sc., NTT", 26000, ["Sensory Play"]),
]

STAFF = [
    ("Latha", "Devi", "female", "Front Office", "Receptionist", "B.Com", 22000,
     ["Admissions desk", "Parent calls"]),
    ("Suresh", "Kumar", "male", "Transport", "Van Driver", "Class 10", 20000,
     ["School van route 1", "Vehicle upkeep"]),
    ("Kamala", "Bai", "female", "Child Care", "Ayah / Helper", "Class 8", 16000,
     ["Toilet training", "Nap time", "Feeding"]),
    ("Geeta", "Shetty", "female", "Child Care", "Senior Care Taker", "B.A.", 21000,
     ["Daycare supervision", "Parent handover"]),
    ("Ramesh", "Yadav", "male", "Security", "Security Guard", "Class 10", 18000,
     ["Gate duty", "Visitor register"]),
    ("Shanti", "Rao", "female", "Kitchen", "Cook", "Class 8", 17000,
     ["Snacks", "Hygiene"]),
    ("Ganesh", "Pawar", "male", "Housekeeping", "Housekeeping Attendant", None, 15000,
     ["Classroom cleaning", "Play area"]),
]

FIRST_NAMES = [
    "Aarav", "Diya", "Vihaan", "Anaya", "Kabir", "Myra", "Reyansh", "Saanvi", "Arjun",
    "Aadhya", "Ishaan", "Kiara", "Advik", "Pari", "Rudra", "Navya", "Ayaan", "Riya",
    "Vivaan", "Anika", "Shaurya", "Ira", "Dhruv", "Sara",
]
LAST_NAMES = ["Sharma", "Patel", "Reddy", "Nair", "Iyer", "Gupta", "Singh", "Khan", "Das", "Mehta"]
OCCUPATIONS = ["Software Engineer", "Doctor", "Teacher", "Business Owner", "Architect",
               "Banker", "Designer", "Consultant"]
BLOOD_GROUPS = ["A+", "B+", "O+", "AB+", "A-", "O-"]
MODES = ["cash", "upi", "card", "cheque", "bank_transfer"]


def _dt(value: date) -> datetime:
    return datetime.combine(value, time(10, 30), tzinfo=timezone.utc)


async def seed(reset: bool = False) -> None:
    await connect_to_mongo()
    db = get_db()

    if reset:
        for name in COLLECTIONS:
            await db[name].delete_many({})
        print("Cleared all collections.")

    # ---- users ----
    if await db.users.count_documents({}) == 0:
        await db.users.insert_many(
            [
                {
                    "name": settings.admin_name, "email": settings.admin_email.lower(),
                    "role": "admin", "is_active": True, "phone": "+91 98765 43210",
                    "password_hash": hash_password(settings.admin_password),
                    "created_at": now_utc(),
                },
                {
                    "name": "Front Office", "email": "office@school.com", "role": "staff",
                    "is_active": True, "phone": "+91 98765 11111",
                    "password_hash": hash_password("office123"), "created_at": now_utc(),
                },
            ]
        )
        print(f"Users created: {settings.admin_email} / office@school.com")

    if await db.students.count_documents({}) > 0:
        print("Students already exist — skipping demo data. Use --reset to rebuild.")
        await close_mongo_connection()
        return

    random.seed(7)
    today = date.today()

    # ---- teachers ----
    teacher_ids = []
    for first, last, gender, designation, qualification, salary, subjects in TEACHERS:
        doc = {
            "employee_no": await next_employee_no(db),
            "first_name": first, "last_name": last, "gender": gender,
            "date_of_birth": encode_dates(today - timedelta(days=365 * random.randint(28, 45))),
            "phone": f"+91 9{random.randint(100000000, 999999999)}",
            "email": f"{first.lower()}.{last.lower()}@littlestars.edu",
            "address": f"{random.randint(1, 90)} Rose Street, Bengaluru",
            "qualification": qualification, "designation": designation, "subjects": subjects,
            "date_of_joining": encode_dates(today - timedelta(days=random.randint(200, 1800))),
            "salary": salary, "status": "active", "notes": None, "created_at": now_utc(),
        }
        result = await db.teachers.insert_one(doc)
        teacher_ids.append(str(result.inserted_id))
    print(f"Teachers created: {len(teacher_ids)}")

    # ---- non-teaching staff ----
    staff_count = 0
    for first, last, gender, department, designation, qualification, salary, duties in STAFF:
        await db.staff.insert_one(
            {
                "employee_no": await next_employee_no(db),
                "first_name": first, "last_name": last, "gender": gender,
                "date_of_birth": encode_dates(
                    today - timedelta(days=365 * random.randint(24, 52))
                ),
                "phone": f"+91 9{random.randint(100000000, 999999999)}",
                "email": None,
                "address": f"{random.randint(1, 90)} Rose Street, Bengaluru",
                "qualification": qualification,
                "department": department, "designation": designation, "duties": duties,
                "date_of_joining": encode_dates(
                    today - timedelta(days=random.randint(200, 1800))
                ),
                "salary": salary,
                "emergency_contact": f"+91 9{random.randint(100000000, 999999999)}",
                "status": "active", "notes": None, "created_at": now_utc(),
            }
        )
        staff_count += 1
    print(f"Non-teaching staff created: {staff_count}")

    # ---- classrooms ----
    classroom_ids = []
    for idx, spec in enumerate(CLASSES):
        doc = {
            **spec,
            "academic_year": settings.academic_year,
            "class_teacher_id": teacher_ids[idx % len(teacher_ids)],
            "created_at": now_utc(),
        }
        result = await db.classrooms.insert_one(doc)
        classroom_ids.append((str(result.inserted_id), spec))
    print(f"Classrooms created: {len(classroom_ids)}")

    # ---- students + payments ----
    student_count = 0
    payment_count = 0
    for classroom_id, spec in classroom_ids:
        for _ in range(random.randint(5, 8)):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            gender = "male" if FIRST_NAMES.index(first) % 2 == 0 else "female"
            age_years = {
                "Pre-Nursery / Play Group": 2,
                "Nursery / Montessori-1": 3,
                "LKG / Montessori-2": 4,
                "UKG / Montessori-3": 5,
            }[spec["level"]]
            discount = random.choice([0, 0, 0, 2000, 5000])

            plan = build_fee_plan(
                spec["fee_components"],
                academic_year=settings.academic_year,
                discount=discount,
                discount_reason="Sibling concession" if discount else None,
            )
            student = {
                "admission_no": await next_admission_no(db),
                "first_name": first, "last_name": last, "gender": gender,
                "date_of_birth": encode_dates(
                    today - timedelta(days=365 * age_years + random.randint(0, 300))
                ),
                "classroom_id": classroom_id,
                "admission_date": encode_dates(today - timedelta(days=random.randint(20, 300))),
                "status": "active", "photo_url": None,
                "guardian": {
                    "father_name": f"{random.choice(['Rajesh', 'Amit', 'Suresh', 'Imran'])} {last}",
                    "father_occupation": random.choice(OCCUPATIONS),
                    "mother_name": f"{random.choice(['Sunita', 'Kavya', 'Neha', 'Asha'])} {last}",
                    "mother_occupation": random.choice(OCCUPATIONS),
                    "guardian_name": None, "relation": "Parent",
                    "primary_phone": f"+91 9{random.randint(100000000, 999999999)}",
                    "alternate_phone": None,
                    "email": f"{first.lower()}.parent@example.com",
                    "address": f"{random.randint(1, 120)}, Green Park, Bengaluru 5600{random.randint(10, 99)}",
                },
                "medical": {
                    "blood_group": random.choice(BLOOD_GROUPS),
                    "allergies": random.choice([None, None, "Peanuts", "Dust"]),
                    "conditions": None, "doctor_name": "Dr. S. Rao",
                    "doctor_phone": "+91 98800 12345",
                },
                "transport_opted": random.random() < 0.4,
                "transport_route": None, "notes": None,
                "fee_plan": encode_dates(plan),
                "created_at": now_utc() - timedelta(days=random.randint(1, 120)),
            }
            if student["transport_opted"]:
                student["transport_route"] = random.choice(["Route 1 - Jayanagar",
                                                            "Route 2 - Koramangala"])
            result = await db.students.insert_one(student)
            student_id = str(result.inserted_id)
            student_count += 1

            # 0-3 receipts per child
            paid_so_far = 0.0
            for n in range(random.choice([0, 1, 1, 2, 2, 3])):
                remaining = plan["net_payable"] - paid_so_far
                if remaining <= 0:
                    break
                amount = money(min(remaining, random.choice([5000, 8000, 12000, 15000, 20000])))
                paid_on = today - timedelta(days=random.randint(1, 150) + n * 5)
                items = auto_allocate_items(plan["installments"], paid_so_far, amount)
                await db.payments.insert_one(
                    {
                        "receipt_no": await next_receipt_no(db, settings.academic_year),
                        "student_id": student_id,
                        "student_name": f"{first} {last}",
                        "admission_no": student["admission_no"],
                        "classroom_name": spec["name"],
                        "academic_year": settings.academic_year,
                        "amount": amount, "mode": random.choice(MODES),
                        "reference": None,
                        "remarks": "Initial admission payment" if n == 0 else None,
                        "items": items, "paid_on": _dt(paid_on),
                        "collected_by": settings.admin_name, "cancelled": False,
                        "balance_after": money(plan["net_payable"] - paid_so_far - amount),
                        "created_at": now_utc(),
                    }
                )
                paid_so_far = money(paid_so_far + amount)
                payment_count += 1

    print(f"Students created: {student_count}")
    print(f"Receipts created: {payment_count}")

    # ---- attendance for the last 10 weekdays ----
    marks = 0
    students = await db.students.find({}, {"classroom_id": 1}).to_list(500)
    day = today
    for _ in range(14):
        if day.weekday() < 5:
            for student in students:
                status = random.choices(["present", "absent", "late"], weights=[88, 8, 4])[0]
                await db.attendance.update_one(
                    {"student_id": str(student["_id"]), "date": encode_dates(day)},
                    {
                        "$set": {
                            "classroom_id": student.get("classroom_id"),
                            "status": status, "remarks": None,
                            "marked_by": settings.admin_name, "updated_at": now_utc(),
                        }
                    },
                    upsert=True,
                )
                marks += 1
        day -= timedelta(days=1)
    print(f"Attendance records: {marks}")

    await close_mongo_connection()
    print("\nDemo data ready. Sign in with "
          f"{settings.admin_email} / {settings.admin_password}")


if __name__ == "__main__":
    asyncio.run(seed(reset="--reset" in sys.argv))
