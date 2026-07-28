"""E2E for the negotiated fee + first-instalment-at-enrolment flow."""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

os.environ["MONGODB_DB"] = "preschool_e2e_temp"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

failures = []


def check(label, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + label + (f"  |  {extra}" if extra else ""))
    if not cond:
        failures.append(label)


GUARDIAN = {"primary_phone": "+91 90000 11111"}

with TestClient(app) as client:
    tok = client.post("/api/auth/login", json={"email": settings.admin_email,
                                               "password": settings.admin_password}).json()
    client.headers["Authorization"] = f"Bearer {tok['access_token']}"

    print("[1] Class with a standard fee structure")
    lkg = client.post("/api/classrooms", json={
        "name": "LKG", "level": "LKG", "capacity": 25, "academic_year": "2026-27",
        "fee_components": [
            {"name": "Admission Fee", "amount": 12000, "frequency": "one_time"},
            {"name": "Tuition Fee", "amount": 5000, "frequency": "monthly"},
            {"name": "Books & Uniform", "amount": 6500, "frequency": "annual"},
        ],
    }).json()
    standard = 12000 + 5000 * 12 + 6500  # 78,500
    check("LKG standard annual fee", lkg["annual_fee"] == standard, str(lkg["annual_fee"]))
    check("fee components returned for the dropdown preview",
          len(lkg["fee_components"]) == 3)

    print("\n[2] Enrol with the standard fee (no negotiation)")
    s1 = client.post("/api/students", json={
        "first_name": "Standard", "last_name": "Child", "date_of_birth": "2021-05-10",
        "classroom_id": lkg["id"], "guardian": GUARDIAN,
    }).json()
    check("plan uses the class standard", s1["fee_plan"]["net_payable"] == standard,
          str(s1["fee_plan"]["net_payable"]))
    check("no concession recorded", s1["fee_plan"]["discount"] == 0)
    check("fee_summary on the student", s1["fee_summary"]["balance"] == standard,
          str(s1["fee_summary"]))

    print("\n[3] Enrol with a NEGOTIATED lower fee")
    agreed = 70000.0
    s2 = client.post("/api/students", json={
        "first_name": "Negotiated", "last_name": "Child", "date_of_birth": "2021-06-10",
        "classroom_id": lkg["id"], "guardian": GUARDIAN,
        "agreed_fee": agreed, "fee_note": "Sibling concession",
    }).json()
    plan = s2["fee_plan"]
    check("net payable is the agreed fee", plan["net_payable"] == agreed, str(plan["net_payable"]))
    check("standard kept for reference", plan["gross"] == standard, str(plan["gross"]))
    check("concession derived", plan["discount"] == standard - agreed, str(plan["discount"]))
    check("no 'extra' recorded", plan["extra"] == 0)
    check("reason stored", plan["discount_reason"] == "Sibling concession")
    total = round(sum(i["amount"] for i in plan["installments"]), 2)
    check("instalments sum to the agreed fee", total == agreed, f"{total} vs {agreed}")
    check("concession spread, not dumped on month 1",
          plan["installments"][0]["amount"] < 12000 + 5000 + 6500,
          str(plan["installments"][0]["amount"]))

    print("\n[4] Enrol with an agreed fee ABOVE standard")
    s3 = client.post("/api/students", json={
        "first_name": "Premium", "last_name": "Child", "date_of_birth": "2021-07-10",
        "classroom_id": lkg["id"], "guardian": GUARDIAN,
        "agreed_fee": 85000, "fee_note": "Includes transport",
    }).json()
    check("extra recorded", s3["fee_plan"]["extra"] == 85000 - standard, str(s3["fee_plan"]["extra"]))
    check("discount stays zero", s3["fee_plan"]["discount"] == 0)
    check("instalments sum to 85000",
          round(sum(i["amount"] for i in s3["fee_plan"]["installments"]), 2) == 85000)

    print("\n[5] Enrol + collect the FIRST INSTALMENT in one step")
    r = client.post("/api/students", json={
        "first_name": "Paid", "last_name": "Upfront", "date_of_birth": "2021-08-10",
        "classroom_id": lkg["id"], "guardian": GUARDIAN,
        "agreed_fee": 60000,
        "initial_payment": {"amount": 15000, "mode": "upi", "reference": "UPI-777",
                            "remarks": "Initial admission payment"},
    })
    check("enrolment accepted", r.status_code == 201, r.text[:200])
    s4 = r.json()
    receipt = s4["initial_receipt"]
    check("receipt issued with the enrolment", receipt is not None)
    check("receipt number present", receipt and receipt["receipt_no"].startswith("RCP/"),
          receipt and receipt["receipt_no"])
    check("receipt amount", receipt["amount"] == 15000)
    check("allocated to the first instalment", "Apr 2026" in receipt["items"][0]["name"],
          receipt["items"][0]["name"])
    check("balance after recorded", receipt["balance_after"] == 45000,
          str(receipt["balance_after"]))
    check("student fee_summary shows the payment", s4["fee_summary"]["total_paid"] == 15000,
          str(s4["fee_summary"]))
    check("student fee_summary balance", s4["fee_summary"]["balance"] == 45000)

    pdf = client.get(f"/api/fees/receipts/{receipt['id']}/pdf")
    check("receipt PDF downloads", pdf.status_code == 200 and pdf.content[:4] == b"%PDF",
          f"{len(pdf.content)} bytes")

    ledger = client.get(f"/api/fees/ledger/{s4['id']}").json()
    check("ledger agrees with the enrolment receipt", ledger["total_paid"] == 15000
          and ledger["balance"] == 45000, str((ledger["total_paid"], ledger["balance"])))

    print("\n[6] Enrol with NO class but an agreed fee")
    s5 = client.post("/api/students", json={
        "first_name": "NoClass", "last_name": "Child", "date_of_birth": "2021-09-10",
        "guardian": GUARDIAN, "agreed_fee": 30000,
    }).json()
    check("plan built without a class", s5["fee_plan"]["net_payable"] == 30000)
    check("single instalment created", len(s5["fee_plan"]["installments"]) == 1,
          str(len(s5["fee_plan"]["installments"])))

    print("\n[7] Dues tracking in the children list")
    lst = client.get("/api/students", params={"page_size": 50}).json()
    check("totals block present", lst.get("totals") is not None)
    expected_total = standard + agreed + 85000 + 60000 + 30000
    check("total fee across all children", lst["totals"]["net_payable"] == expected_total,
          f"{lst['totals']['net_payable']} vs {expected_total}")
    check("collected total", lst["totals"]["total_paid"] == 15000, str(lst["totals"]["total_paid"]))
    check("pending due total", lst["totals"]["balance"] == expected_total - 15000)

    pending = client.get("/api/students", params={"dues": "pending", "page_size": 50}).json()
    check("dues=pending returns everyone with a balance", pending["total"] == 5,
          str(pending["total"]))
    clear = client.get("/api/students", params={"dues": "clear", "page_size": 50}).json()
    check("dues=clear returns nobody yet", clear["total"] == 0, str(clear["total"]))

    # Pay one child off completely, then re-check the filters.
    client.post("/api/fees/payments", json={"student_id": s5["id"], "amount": 30000,
                                            "mode": "cash"})
    clear2 = client.get("/api/students", params={"dues": "clear", "page_size": 50}).json()
    check("fully-paid child moves to dues=clear", clear2["total"] == 1, str(clear2["total"]))
    check("cleared child has zero balance",
          clear2["items"][0]["fee_summary"]["balance"] == 0)

    print("\n[8] Re-negotiating the fee later")
    r = client.post(f"/api/students/{s4['id']}/fee-plan",
                    json={"use_classroom_structure": True, "agreed_fee": 50000,
                          "discount_reason": "Revised after discussion"})
    check("fee plan updated", r.status_code == 200, r.text[:200])
    check("new agreed total", r.json()["fee_plan"]["net_payable"] == 50000)
    ledger2 = client.get(f"/api/fees/ledger/{s4['id']}").json()
    check("earlier payment untouched", ledger2["total_paid"] == 15000, str(ledger2["total_paid"]))
    check("balance recomputed against the new total", ledger2["balance"] == 35000,
          str(ledger2["balance"]))

    print("\n[9] Guard rails")
    check("initial payment of 0 rejected",
          client.post("/api/students", json={
              "first_name": "Bad", "date_of_birth": "2021-01-01", "guardian": GUARDIAN,
              "initial_payment": {"amount": 0, "mode": "cash"}}).status_code == 422)
    check("negative agreed fee rejected",
          client.post("/api/students", json={
              "first_name": "Bad", "date_of_birth": "2021-01-01", "guardian": GUARDIAN,
              "agreed_fee": -100}).status_code == 422)

print("\n[10] Cleanup")
import asyncio  # noqa: E402

from pymongo import AsyncMongoClient  # noqa: E402


async def drop():
    c = AsyncMongoClient(settings.mongodb_uri)
    await c.drop_database("preschool_e2e_temp")
    names = await c.list_database_names()
    await c.close()
    return names


check("test database dropped", "preschool_e2e_temp" not in asyncio.run(drop()))

print("\n" + ("ALL FEE-FLOW CHECKS PASSED" if not failures else f"{len(failures)} FAILURES: {failures}"))
sys.exit(1 if failures else 0)
