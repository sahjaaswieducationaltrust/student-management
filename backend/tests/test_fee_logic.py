"""Offline smoke test: fee maths, receipt PDF, OpenAPI schema.

Needs no database. Run from anywhere:  python tests/test_fee_logic.py
"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "_output"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(BACKEND))

from app.services.fees import build_fee_plan, summarise, auto_allocate_items, allocate
from app.utils import amount_in_words, money
from app.services.receipt_pdf import build_receipt_pdf

failures = []


def check(label, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + label + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(label)


COMPONENTS = [
    {"name": "Admission Fee", "amount": 10000, "frequency": "one_time"},
    {"name": "Tuition Fee", "amount": 4200, "frequency": "monthly"},
    {"name": "Activity Kit", "amount": 3000, "frequency": "term"},
    {"name": "Annual Day", "amount": 4000, "frequency": "annual"},
]

print("\n[1] Fee plan generation")
plan = build_fee_plan(COMPONENTS, academic_year="2026-27")
expected_gross = 10000 + 4200 * 12 + 3000 * 3 + 4000
check("gross = sum(component x occurrences)", plan["gross"] == expected_gross,
      f"{plan['gross']} vs {expected_gross}")
check("12 monthly instalments", len(plan["installments"]) == 12, str(len(plan["installments"])))
check("first instalment due Apr 2026", plan["installments"][0]["due_date"] == date(2026, 4, 1),
      str(plan["installments"][0]["due_date"]))
check("first instalment bundles one-time + annual + term + monthly",
      plan["installments"][0]["amount"] == 10000 + 4200 + 3000 + 4000,
      str(plan["installments"][0]["amount"]))
check("sum(instalments) == net_payable",
      money(sum(i["amount"] for i in plan["installments"])) == plan["net_payable"])

print("\n[2] Discount spread proportionally")
disc = build_fee_plan(COMPONENTS, academic_year="2026-27", discount=5000, discount_reason="Sibling")
check("net = gross - discount", disc["net_payable"] == expected_gross - 5000,
      str(disc["net_payable"]))
check("sum(instalments) == net_payable after discount",
      money(sum(i["amount"] for i in disc["installments"])) == disc["net_payable"],
      f"{money(sum(i['amount'] for i in disc['installments']))} vs {disc['net_payable']}")
check("no negative instalment", all(i["amount"] >= 0 for i in disc["installments"]))

print("\n[3] Payment allocation (earliest due first)")
first_due = plan["installments"][0]["amount"]
rows = allocate(plan["installments"], first_due, today=date(2026, 4, 15))
check("first instalment fully paid", rows[0]["status"] == "paid" and rows[0]["balance"] == 0)
check("second instalment untouched", rows[1]["paid"] == 0)
partial = allocate(plan["installments"], first_due + 1000, today=date(2026, 4, 15))
check("overflow lands on next instalment", partial[1]["paid"] == 1000, str(partial[1]["paid"]))
check("partial status", partial[1]["status"] == "partial", partial[1]["status"])
overdue = allocate(plan["installments"], 0, today=date(2026, 8, 15))
check("past-due unpaid rows are overdue, future rows are due",
      [r["status"] for r in overdue[:6]] == ["overdue"] * 5 + ["due"],
      str([f"{r['label']}:{r['status']}" for r in overdue[:6]]))

print("\n[4] Ledger summary")
summary = summarise(plan, 25000)
check("balance = net - paid", summary["balance"] == money(plan["net_payable"] - 25000),
      str(summary["balance"]))
check("next_due points at the first unpaid row", summary["next_due"] is not None
      and summary["next_due"]["balance"] > 0)
check("total_paid echoed", summary["total_paid"] == 25000)

print("\n[5] Auto-allocated receipt line items")
items = auto_allocate_items(plan["installments"], already_paid=0, new_amount=25000)
check("line items total the payment", money(sum(i["amount"] for i in items)) == 25000,
      str(sum(i["amount"] for i in items)))
check("line items name the instalment + components", "Apr 2026" in items[0]["name"], items[0]["name"])
advance = auto_allocate_items(plan["installments"], already_paid=plan["net_payable"], new_amount=500)
check("overpayment becomes an advance line", advance[-1]["name"] == "Advance / Other")

print("\n[6] Amount in words (Indian numbering)")
cases = [
    (0, "Rupees Zero Only"),
    (500, "Rupees Five Hundred Only"),
    (21200, "Rupees Twenty One Thousand Two Hundred Only"),
    (100000, "Rupees One Lakh Only"),
    (1250500.50, "Rupees Twelve Lakh Fifty Thousand Five Hundred and Fifty Paise Only"),
    (10000000, "Rupees One Crore Only"),
]
for value, expected in cases:
    got = amount_in_words(value)
    check(f"{value} -> {expected}", got == expected, f"got: {got}")

print("\n[7] Receipt PDF")
payment = {
    "receipt_no": "RCP/2026-27/00001",
    "student_name": "Aarav Sharma",
    "admission_no": "ADM20260001",
    "classroom_name": "Nursery A",
    "academic_year": "2026-27",
    "amount": 25000,
    "mode": "bank_transfer",
    "reference": "UTR8891233",
    "remarks": "Initial admission payment",
    "items": items,
    "paid_on": datetime(2026, 4, 12, tzinfo=timezone.utc),
    "collected_by": "Administrator",
    "cancelled": False,
}
pdf = build_receipt_pdf(payment, summary)
check("PDF built", pdf[:4] == b"%PDF" and len(pdf) > 2000, f"{len(pdf)} bytes")
(OUT / "sample-receipt.pdf").write_bytes(pdf)
cancelled_pdf = build_receipt_pdf({**payment, "cancelled": True, "cancel_reason": "Cheque bounced"}, summary)
check("cancelled variant builds", cancelled_pdf[:4] == b"%PDF")

print("\n[8] FastAPI app / OpenAPI schema")
from app.main import app
schema = app.openapi()
paths = sorted(schema["paths"])
check("routes registered", len(paths) >= 20, f"{len(paths)} paths")
for expected in ["/api/auth/login", "/api/students", "/api/fees/payments",
                 "/api/fees/receipts/{payment_id}/pdf", "/api/attendance", "/api/dashboard"]:
    check(f"route {expected}", expected in paths)

print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILURES: {failures}"))
sys.exit(1 if failures else 0)
