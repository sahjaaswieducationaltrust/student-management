"""End-to-end test against the real Atlas cluster, in a throwaway database.

Uses MONGODB_DB=preschool_e2e_temp (env vars beat the .env file), then drops
that database at the end so the real `preschool` database is never touched.
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "_output"
OUT.mkdir(exist_ok=True)

os.environ["MONGODB_DB"] = "preschool_e2e_temp"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

assert settings.mongodb_db == "preschool_e2e_temp", settings.mongodb_db
print(f"Test database: {settings.mongodb_db}  (real data untouched)\n")

failures = []


def check(label, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + label + (f"  |  {extra}" if extra else ""))
    if not cond:
        failures.append(label)


with TestClient(app) as client:
    print("[1] Auth")
    r = client.post("/api/auth/login",
                    json={"email": settings.admin_email, "password": settings.admin_password})
    check("admin can sign in", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}")
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    check("role is admin", r.json()["user"]["role"] == "admin")
    check("wrong password rejected",
          client.post("/api/auth/login",
                      json={"email": settings.admin_email, "password": "nope"}).status_code == 401)
    check("unauthenticated request rejected",
          client.get("/api/students", headers={"Authorization": "Bearer bad"}).status_code == 401)

    print("\n[2] Teacher, non-teaching staff + class with a fee structure")
    r = client.post("/api/teachers", json={
        "first_name": "Meera", "last_name": "Nair", "phone": "+91 98765 43210",
        "designation": "Class Teacher", "qualification": "M.A., B.Ed", "salary": 42000,
    })
    check("teacher created", r.status_code == 201, r.text[:150])
    teacher = r.json()
    check("employee number auto-generated", teacher["employee_no"].startswith("EMP"),
          teacher["employee_no"])

    r = client.post("/api/staff", json={
        "first_name": "Latha", "last_name": "Devi", "phone": "+91 98765 11111",
        "department": "Front Office", "designation": "Receptionist",
        "duties": ["Admissions desk", "Parent calls"], "salary": 22000,
    })
    check("non-teaching staff created", r.status_code == 201, r.text[:150])
    helper = r.json()
    check("staff employee number auto-generated", helper["employee_no"].startswith("EMP"),
          helper["employee_no"])
    check("staff share one employee-number sequence with teachers",
          helper["employee_no"] != teacher["employee_no"],
          f"{teacher['employee_no']} vs {helper['employee_no']}")
    check("staff kept out of the teacher list",
          all(t["id"] != helper["id"] for t in client.get("/api/teachers").json()))
    check("department filter matches",
          len(client.get("/api/staff", params={"department": "Front Office"}).json()) == 1)
    check("department filter excludes others",
          client.get("/api/staff", params={"department": "Kitchen"}).json() == [])
    check("staff search by designation",
          len(client.get("/api/staff", params={"search": "reception"}).json()) == 1)
    check("departments in use listed",
          client.get("/api/staff/departments").json() == ["Front Office"])
    r = client.patch(f"/api/staff/{helper['id']}", json={"salary": 24000, "status": "inactive"})
    check("staff record updated", r.status_code == 200 and r.json()["salary"] == 24000, r.text[:150])
    check("inactive staff hidden by the active filter",
          client.get("/api/staff", params={"status": "active"}).json() == [])
    client.patch(f"/api/staff/{helper['id']}", json={"status": "active"})

    r = client.post("/api/classrooms", json={
        "name": "Nursery A", "level": "Nursery", "room": "Rainbow", "capacity": 20,
        "academic_year": "2026-27", "class_teacher_id": teacher["id"],
        "fee_components": [
            {"name": "Admission Fee", "amount": 10000, "frequency": "one_time"},
            {"name": "Tuition Fee", "amount": 4200, "frequency": "monthly"},
            {"name": "Activity Kit", "amount": 3000, "frequency": "term"},
        ],
    })
    check("class created", r.status_code == 201, r.text[:150])
    classroom = r.json()
    expected_annual = 10000 + 4200 * 12 + 3000 * 3
    check("annual fee computed", classroom["annual_fee"] == expected_annual,
          f"{classroom['annual_fee']} vs {expected_annual}")
    check("class teacher resolved", classroom["class_teacher_name"] == "Meera Nair")

    print("\n[3] Enrol a child (fee plan should be automatic)")
    r = client.post("/api/students", json={
        "first_name": "Aarav", "last_name": "Sharma", "gender": "male",
        "date_of_birth": "2023-06-15", "classroom_id": classroom["id"],
        "guardian": {"father_name": "Rajesh Sharma", "mother_name": "Sunita Sharma",
                     "primary_phone": "+91 90000 11111", "email": "rajesh@example.com",
                     "address": "12 Green Park, Bengaluru"},
        "medical": {"blood_group": "O+", "allergies": "Peanuts"},
    })
    check("child enrolled", r.status_code == 201, r.text[:200])
    student = r.json()
    check("admission number auto-generated", student["admission_no"].startswith("ADM"),
          student["admission_no"])
    check("age derived from DOB", student["age"] is not None, str(student["age"]))
    check("class name resolved", student["classroom_name"] == "Nursery A")
    check("fee plan auto-built from class", student["fee_plan"] is not None)
    plan = student["fee_plan"]
    check("net payable matches annual fee", plan["net_payable"] == expected_annual,
          str(plan["net_payable"]))
    check("12 instalments scheduled", len(plan["installments"]) == 12,
          str(len(plan["installments"])))

    print("\n[4] Ledger before payment")
    r = client.get(f"/api/fees/ledger/{student['id']}")
    check("ledger loads", r.status_code == 200, r.text[:150])
    ledger = r.json()
    check("nothing paid yet", ledger["total_paid"] == 0)
    check("balance == net payable", ledger["balance"] == expected_annual)
    first_due = ledger["next_due"]
    check("next due is the first instalment", first_due["label"].startswith("Apr"),
          first_due["label"])
    check("first instalment bundles admission + tuition + kit",
          first_due["amount"] == 10000 + 4200 + 3000, str(first_due["amount"]))

    print("\n[5] Collect the initial admission payment -> receipt")
    r = client.post("/api/fees/payments", json={
        "student_id": student["id"], "amount": first_due["amount"], "mode": "upi",
        "reference": "UPI-8891233", "remarks": "Initial admission payment",
    })
    check("payment accepted", r.status_code == 201, r.text[:200])
    payment = r.json()
    check("receipt number issued", payment["receipt_no"].startswith("RCP/2026-27/"),
          payment["receipt_no"])
    check("receipt lines auto-allocated", len(payment["items"]) >= 1,
          str([i["name"] for i in payment["items"]]))
    check("line items total the payment",
          round(sum(i["amount"] for i in payment["items"]), 2) == first_due["amount"])
    check("balance_after recorded",
          payment["balance_after"] == round(expected_annual - first_due["amount"], 2),
          str(payment["balance_after"]))

    print("\n[6] Receipt document + PDF")
    r = client.get(f"/api/fees/receipts/{payment['id']}")
    check("receipt data loads", r.status_code == 200, r.text[:150])
    receipt = r.json()
    check("amount in words present", "Rupees" in receipt["amount_in_words"],
          receipt["amount_in_words"])
    check("school header included", receipt["school"]["name"] == settings.school_full_name,
          receipt["school"]["name"])
    check("branch tagline on the receipt",
          receipt["school"]["tagline"] == settings.school_tagline)
    check("branch contact on the receipt",
          receipt["school"]["phone"] == settings.school_phone
          and receipt["school"]["email"] == settings.school_email,
          f"{receipt['school']['phone']} / {receipt['school']['email']}")
    check("balance shown on receipt",
          receipt["balance"] == round(expected_annual - first_due["amount"], 2))

    r = client.get(f"/api/fees/receipts/{payment['id']}/pdf")
    check("PDF served", r.status_code == 200 and r.content[:4] == b"%PDF",
          f"HTTP {r.status_code}, {len(r.content)} bytes")
    check("PDF content-type", r.headers["content-type"] == "application/pdf")
    (OUT / "e2e-receipt.pdf").write_bytes(r.content)

    print("\n[7] Ledger after payment")
    ledger2 = client.get(f"/api/fees/ledger/{student['id']}").json()
    check("paid total updated", ledger2["total_paid"] == first_due["amount"],
          str(ledger2["total_paid"]))
    check("balance reduced", ledger2["balance"] == round(expected_annual - first_due["amount"], 2))
    check("first instalment marked paid", ledger2["installments"][0]["status"] == "paid",
          ledger2["installments"][0]["status"])
    check("next due moved to May", ledger2["next_due"]["label"].startswith("May"),
          ledger2["next_due"]["label"])
    check("payment appears in history", len(ledger2["payments"]) == 1)

    print("\n[8] Second payment lands on the next instalment")
    r = client.post("/api/fees/payments",
                    json={"student_id": student["id"], "amount": 4200, "mode": "cash"})
    check("second receipt created", r.status_code == 201, r.text[:150])
    p2 = r.json()
    check("receipt numbers increment", p2["receipt_no"] != payment["receipt_no"],
          f"{payment['receipt_no']} -> {p2['receipt_no']}")
    check("allocated to May", "May 2026" in p2["items"][0]["name"], p2["items"][0]["name"])

    print("\n[9] Receipt list + dues report")
    r = client.get("/api/fees/payments", params={"page_size": 50})
    check("receipt list works", r.status_code == 200 and r.json()["total"] == 2,
          str(r.json().get("total")))
    check("collected total correct",
          r.json()["total_amount"] == round(first_due["amount"] + 4200, 2),
          str(r.json()["total_amount"]))
    dues = client.get("/api/fees/dues").json()
    check("child appears in dues", len(dues) == 1 and dues[0]["student_id"] == student["id"])
    check("dues balance correct",
          dues[0]["balance"] == round(expected_annual - first_due["amount"] - 4200, 2),
          str(dues[0]["balance"]))

    print("\n[10] Attendance")
    r = client.get("/api/attendance", params={"classroom_id": classroom["id"], "date": "2026-07-27"})
    check("roll-call sheet lists the child", r.status_code == 200 and len(r.json()) == 1,
          r.text[:150])
    r = client.post("/api/attendance", json={
        "classroom_id": classroom["id"], "date": "2026-07-27",
        "entries": [{"student_id": student["id"], "status": "present"}],
    })
    check("attendance saved", r.status_code == 200, r.text[:150])
    r = client.post("/api/attendance", json={
        "classroom_id": classroom["id"], "date": "2026-07-27",
        "entries": [{"student_id": student["id"], "status": "late", "remarks": "Traffic"}],
    })
    check("re-saving updates instead of duplicating",
          r.status_code == 200 and r.json()["created"] == 0, r.text[:150])
    hist = client.get(f"/api/attendance/student/{student['id']}").json()
    check("attendance history reads back", hist["counts"]["late"] == 1, str(hist["counts"]))

    print("\n[11] Dashboard + reports")
    d = client.get("/api/dashboard").json()
    check("dashboard: 1 active child", d["students_active"] == 1)
    check("dashboard: 1 teacher", d["teachers_active"] == 1)
    check("dashboard: 1 non-teaching staff", d["staff_active"] == 1, str(d["staff_active"]))
    check("dashboard: fees expected", d["fees_expected"] == expected_annual, str(d["fees_expected"]))
    check("dashboard: fees collected",
          d["fees_collected"] == round(first_due["amount"] + 4200, 2), str(d["fees_collected"]))
    check("dashboard: outstanding",
          d["fees_outstanding"] == round(expected_annual - first_due["amount"] - 4200, 2))
    check("dashboard: recent receipts listed", len(d["recent_payments"]) == 2)
    s = client.get("/api/fees/summary").json()
    check("summary by mode has upi + cash", {m["key"] for m in s["by_mode"]} == {"upi", "cash"},
          str([m["key"] for m in s["by_mode"]]))

    print("\n[12] Cancel a receipt (admin only)")
    r = client.post(f"/api/fees/payments/{p2['id']}/cancel", params={"reason": "Entered twice"})
    check("receipt cancelled", r.status_code == 200 and r.json()["cancelled"], r.text[:150])
    ledger3 = client.get(f"/api/fees/ledger/{student['id']}").json()
    check("cancelled amount removed from paid total",
          ledger3["total_paid"] == first_due["amount"], str(ledger3["total_paid"]))
    check("cancelling twice is rejected",
          client.post(f"/api/fees/payments/{p2['id']}/cancel",
                      params={"reason": "again"}).status_code == 400)

    print("\n[13] Role enforcement (staff account)")
    r = client.post("/api/users", json={"name": "Front Office", "email": "office@frontdesk.example.com",
                                        "role": "staff", "password": "office123"})
    check("staff user created", r.status_code == 201, r.text[:150])
    staff_token = client.post("/api/auth/login",
                              json={"email": "office@frontdesk.example.com",
                                    "password": "office123"}).json()["access_token"]
    staff = {"Authorization": f"Bearer {staff_token}"}
    check("staff can collect fees",
          client.post("/api/fees/payments", headers=staff,
                      json={"student_id": student["id"], "amount": 100,
                            "mode": "cash"}).status_code == 201)
    check("staff cannot delete a child",
          client.delete(f"/api/students/{student['id']}", headers=staff).status_code == 403)
    check("staff cannot cancel a receipt",
          client.post(f"/api/fees/payments/{payment['id']}/cancel", headers=staff,
                      params={"reason": "test"}).status_code == 403)
    check("staff cannot list users", client.get("/api/users", headers=staff).status_code == 403)
    check("staff can add a non-teaching staff member",
          client.post("/api/staff", headers=staff,
                      json={"first_name": "Ramesh", "phone": "+91 98765 22222",
                            "department": "Security",
                            "designation": "Security Guard"}).status_code == 201)
    check("staff cannot delete a non-teaching staff member",
          client.delete(f"/api/staff/{helper['id']}", headers=staff).status_code == 403)

    print("\n[14] Validation + guard rails")
    check("child with receipts cannot be deleted",
          client.delete(f"/api/students/{student['id']}").status_code == 409)
    check("class with children cannot be deleted",
          client.delete(f"/api/classrooms/{classroom['id']}").status_code == 409)
    check("future date of birth rejected",
          client.post("/api/students", json={
              "first_name": "X", "date_of_birth": "2099-01-01",
              "guardian": {"primary_phone": "+91 90000 00000"}}).status_code == 422)
    check("zero-amount payment rejected",
          client.post("/api/fees/payments",
                      json={"student_id": student["id"], "amount": 0,
                            "mode": "cash"}).status_code == 422)
    check("duplicate user email rejected",
          client.post("/api/users", json={"name": "Dup", "email": "office@frontdesk.example.com",
                                          "role": "staff", "password": "x123456"}).status_code == 409)
    check("bad object id gives 400 not 500",
          client.get("/api/fees/ledger/not-an-id").status_code == 400)
    check("missing child gives 404",
          client.get("/api/students/000000000000000000000000").status_code == 404)

print("\n[15] Cleanup")
import asyncio  # noqa: E402

from pymongo import AsyncMongoClient  # noqa: E402


async def drop():
    c = AsyncMongoClient(settings.mongodb_uri)
    await c.drop_database("preschool_e2e_temp")
    remaining = await c.list_database_names()
    await c.close()
    return remaining


remaining = asyncio.run(drop())
check("test database dropped", "preschool_e2e_temp" not in remaining, str(remaining))

print("\n" + ("ALL E2E CHECKS PASSED" if not failures else f"{len(failures)} FAILURES: {failures}"))
sys.exit(1 if failures else 0)

