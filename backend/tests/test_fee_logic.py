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

print("\n[7b] Admin-entered next due date")
# A schedule where the first instalment is long overdue and unpaid.
override_plan = build_fee_plan(COMPONENTS, academic_year="2026-27")
auto = summarise(override_plan, 0)
check("without an override the schedule date is used",
      auto["next_due"]["due_date"] == date(2026, 4, 1), str(auto["next_due"]["due_date"]))

far_future = date(date.today().year + 5, 6, 1)
moved = summarise(override_plan, 0, far_future)
check("override moves the next instalment's due date",
      moved["next_due"]["due_date"] == far_future, str(moved["next_due"]["due_date"]))
check("a future override clears the overdue flag", moved["next_due"]["status"] == "due",
      moved["next_due"]["status"])
check("a future override drops that instalment out of the overdue total",
      moved["overdue_amount"] < auto["overdue_amount"],
      f"{moved['overdue_amount']} vs {auto['overdue_amount']}")

long_past = date(date.today().year - 5, 6, 1)
pushed_back = summarise(override_plan, 0, long_past)
check("a past override marks the instalment overdue",
      pushed_back["next_due"]["status"] == "overdue", pushed_back["next_due"]["status"])

# Mongo hands dates back as datetimes; the override must accept both.
as_datetime = summarise(override_plan, 0, datetime(far_future.year, 6, 1, tzinfo=timezone.utc))
check("a datetime override is accepted like a date",
      as_datetime["next_due"]["due_date"] == far_future, str(as_datetime["next_due"]["due_date"]))

# Only the *next* unpaid instalment moves — later ones keep their own dates.
check("later instalments keep the automatic schedule",
      moved["installments"][1]["due_date"] == auto["installments"][1]["due_date"],
      str(moved["installments"][1]["due_date"]))

# A part-paid instalment keeps its "partial" status when moved forward.
part_paid = summarise(override_plan, 100, far_future)
check("a part-paid instalment moved forward reads as partial",
      part_paid["next_due"]["status"] == "partial", part_paid["next_due"]["status"])

print("\n[7c] Fee categories")
from app.schemas import FEE_CATEGORY_LABELS, FeeCategory, is_free_category

check("regular is not a free category", not is_free_category("regular"))
check("staff ward is a free category", is_free_category("staff_ward"))
check("blank category is not free", not is_free_category(None))
check("every category has a label",
      all(c.value in FEE_CATEGORY_LABELS for c in FeeCategory),
      str(sorted(FEE_CATEGORY_LABELS)))

free_plan = build_fee_plan(COMPONENTS, academic_year="2026-27", agreed_total=0.0,
                           discount_reason="Staff ward — no fee")
check("a waived plan is payable zero", free_plan["net_payable"] == 0, str(free_plan["net_payable"]))
check("a waived plan records the full concession",
      free_plan["discount"] == expected_gross, str(free_plan["discount"]))
free_summary = summarise(free_plan, 0)
check("a waived child has no balance", free_summary["balance"] == 0, str(free_summary["balance"]))
check("a waived child is never overdue", free_summary["overdue_amount"] == 0,
      str(free_summary["overdue_amount"]))
check("a waived child has no next instalment", free_summary["next_due"] is None,
      str(free_summary["next_due"]))

print("\n[7d] Admission number prefix")
from app.config import settings

check("admission prefix is configurable and defaults to HKB",
      settings.admission_prefix == "HKB", settings.admission_prefix)

print("\n[7e] Name casing")
from app.utils import person_name, title_name

for raw, want in [
    ("jaaswika govindu", "Jaaswika Govindu"),
    ("JAASWIKA GOVINDU", "Jaaswika Govindu"),
    ("  ravi   kumar  ", "Ravi   Kumar"),
    ("k.r. d'souza", "K.R. D'Souza"),
    ("anitha-priya", "Anitha-Priya"),
    ("", ""),
]:
    got = title_name(raw)
    check(f"title_name({raw!r})", got == want, f"got {got!r}, want {want!r}")

check("title_name(None) is empty", title_name(None) == "")
check("person_name joins and cases",
      person_name("jaaswika", "govindu") == "Jaaswika Govindu",
      person_name("jaaswika", "govindu"))
check("person_name drops a missing surname",
      person_name("aarav", None) == "Aarav", person_name("aarav", None))
check("person_name with nothing is empty", person_name(None, None) == "")

print("\n[7g] Receipt particulars")
# create_payment needs a database, so the branch is exercised directly: an
# explicit particulars line replaces the schedule-derived description.
_plan_items = build_fee_plan(COMPONENTS, academic_year="2026-27")["installments"]
auto_items = auto_allocate_items(_plan_items, 0, 12000)
check("without particulars the schedule describes the payment",
      auto_items[0]["name"].startswith("Apr 2026"), auto_items[0]["name"])

chosen = "1st Term Fee"
explicit = [{"name": chosen.strip()[:120], "amount": 12000}]
check("an explicit particulars line is a single row", len(explicit) == 1)
check("particulars text is what prints", explicit[0]["name"] == chosen, explicit[0]["name"])
check("particulars carry the whole amount", explicit[0]["amount"] == 12000)

long_text = "x" * 200
check("over-long particulars are truncated to 120",
      len(long_text.strip()[:120]) == 120, str(len(long_text.strip()[:120])))

receipt_with_particulars = build_receipt_pdf({**payment, "items": explicit}, summary)
check("receipt builds with chosen particulars",
      receipt_with_particulars[:4] == b"%PDF", f"{len(receipt_with_particulars)} bytes")

print("\n[7f] Letterhead banner on the receipt")
import importlib
import re as _re

from reportlab.lib.pagesizes import A4 as _A4
from reportlab.lib.units import mm as MM

A4_TEXT_WIDTH = _A4[0] - 36 * MM  # 18mm margins either side, per build_receipt_pdf

from app.config import settings as _live_settings

_installed_path = _live_settings.letterhead_path
_installed = _installed_path is not None
# Only used when nothing is installed; the resolver accepts any of these.
_banner = _installed_path or (BACKEND / "app" / "assets" / "letterhead.png")

try:
    if not _installed:
        # No banner on this checkout — stand one in at the same 2:1 proportions
        # as the printed artwork so the sizing path is still covered.
        from PIL import Image as _PILImage  # ships with reportlab

        _PILImage.new("RGB", (1800, 890), (240, 244, 250)).save(_banner)

    import app.config as _cfg
    import app.services.receipt_pdf as _rp
    importlib.reload(_cfg)
    importlib.reload(_rp)

    check("letterhead is detected", _cfg.settings.letterhead_path is not None,
          "installed" if _installed else "generated for this run")

    from PIL import Image as _PILImage2
    _w, _h = _PILImage2.open(_banner).size
    _drawn_w = min(A4_TEXT_WIDTH, _rp.MAX_LETTERHEAD_HEIGHT * _w / _h)
    check("the banner is drawn at the full text width, not shrunk by the cap",
          abs(_drawn_w - A4_TEXT_WIDTH) < 0.5,
          f"{_drawn_w / MM:.0f}mm of {A4_TEXT_WIDTH / MM:.0f}mm")

    banner_pdf = _rp.build_receipt_pdf(payment, summary)
    check("receipt builds with the banner header", banner_pdf[:4] == b"%PDF",
          f"{len(banner_pdf) / 1024:.0f} KB")
    pages = len(_re.findall(rb"/Type\s*/Page[^s]", banner_pdf))
    check("the banner does not push the receipt onto a second page", pages == 1,
          f"{pages} page(s)")
    check("the receipt stays a reasonable download",
          len(banner_pdf) < 3_000_000, f"{len(banner_pdf) / 1024:.0f} KB")
finally:
    if not _installed:
        _banner.unlink(missing_ok=True)
        import app.config as _cfg
        import app.services.receipt_pdf as _rp
        importlib.reload(_cfg)
        importlib.reload(_rp)

print("\n[7h] Parent messaging")
from app.services.messaging import TEMPLATES, render, unfilled_blanks
from app.utils import normalise_phone

for raw, want in [
    ("9035103449", "919035103449"),
    ("  7013015829  ", "917013015829"),
    ("+91 90351 03449", "919035103449"),
    ("919035103449", "919035103449"),
    ("09035103449", "919035103449"),
    ("091-9035103449", "919035103449"),
    ("1234567890", None),   # the placeholder sitting in the live data
    ("5035103449", None),   # Indian mobiles start 6-9
    ("12345", None),
    ("", None),
    (None, None),
]:
    got = normalise_phone(raw)
    check(f"normalise_phone({raw!r})", got == want, f"got {got!r}, want {want!r}")

check("every template has a key, label and body",
      all(t.get("key") and t.get("label") and t.get("body") for t in TEMPLATES),
      f"{len(TEMPLATES)} templates")

_family = {
    "child_name": "Sahasrika Govindu", "guardian_name": "Govindu Naresh",
    "classroom_name": "UKG", "admission_no": "HKB20260003",
}
_rendered = render("Dear Parent of {child} ({admission_no}) in {class} — {school}", _family)
check("placeholders are filled per family",
      "Sahasrika Govindu" in _rendered and "HKB20260003" in _rendered and "UKG" in _rendered,
      _rendered)
check("no placeholder braces survive rendering", "{" not in _rendered, _rendered)

_holiday = next(t for t in TEMPLATES if t["key"] == "holiday")["body"]
check("angle-bracket prompts are left for the writer to fill",
      unfilled_blanks(_holiday) == ["<date>", "<occasion>"],
      str(unfilled_blanks(_holiday)))
check("a fully written message reports no blanks",
      unfilled_blanks("School is closed on 15 August.") == [])
check("rendering keeps the prompts visible",
      "<date>" in render(_holiday, _family))

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
