"""Fee plan generation and ledger arithmetic.

A student's *fee plan* is an embedded snapshot on the student document:

    fee_plan = {
        academic_year, items[], installments[], gross, discount,
        discount_reason, net_payable, generated_at
    }

Invariant: ``sum(installment.amount) == net_payable`` — the discount is spread
proportionally over the schedule when the plan is generated, so payments can be
allocated straight against the installments (first-due first).
"""

from datetime import date
from typing import Any

from ..config import settings
from ..utils import money, now_utc

# how many times a component is charged across one academic year
OCCURRENCES: dict[str, int] = {
    "one_time": 1,
    "annual": 1,
    "term": 3,
    "quarterly": 4,
    "monthly": 12,
}

# month offsets from the start of the academic session
OFFSETS: dict[str, list[int]] = {
    "one_time": [0],
    "annual": [0],
    "term": [0, 4, 8],
    "quarterly": [0, 3, 6, 9],
    "monthly": list(range(12)),
}

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def academic_year_start(academic_year: str | None = None) -> date:
    """First day of the session, e.g. "2026-27" -> 2026-04-01."""
    ay = academic_year or settings.academic_year
    try:
        year = int(str(ay).split("-")[0])
    except (ValueError, IndexError):
        year = date.today().year
    return date(year, max(1, min(12, settings.session_start_month)), 1)


def _shift_month(anchor: date, months: int) -> date:
    total = anchor.month - 1 + months
    return date(anchor.year + total // 12, total % 12 + 1, 1)


def build_installments(
    components: list[dict[str, Any]], academic_year: str | None = None
) -> list[dict[str, Any]]:
    """Expand fee components into a dated installment schedule."""
    anchor = academic_year_start(academic_year)
    buckets: dict[date, list[dict[str, Any]]] = {}

    for comp in components:
        amount = money(comp.get("amount"))
        if amount <= 0:
            continue
        freq = comp.get("frequency", "annual")
        for offset in OFFSETS.get(freq, [0]):
            due = _shift_month(anchor, offset)
            buckets.setdefault(due, []).append(
                {"name": comp.get("name", "Fee"), "amount": amount, "frequency": freq}
            )

    schedule = []
    for due in sorted(buckets):
        items = buckets[due]
        schedule.append(
            {
                "label": f"{_MONTHS[due.month - 1]} {due.year}",
                "due_date": due,
                "amount": money(sum(i["amount"] for i in items)),
                "items": items,
            }
        )
    return schedule


def scale_installments(
    installments: list[dict[str, Any]], gross: float, net: float, academic_year: str | None = None
) -> list[dict[str, Any]]:
    """Rescale the schedule so ``sum(installment.amount) == net``.

    The agreed fee is a negotiated total, so the concession (or the extra) is
    spread proportionally over the whole year rather than dumped on month one.
    The last row absorbs rounding drift, which keeps the invariant exact.
    """
    net = money(max(0.0, net))

    if not installments:
        # The class has no fee structure, but a total was agreed anyway — put it
        # in a single instalment at the start of the session.
        if net <= 0:
            return []
        due = academic_year_start(academic_year)
        return [
            {
                "label": f"{_MONTHS[due.month - 1]} {due.year}",
                "due_date": due,
                "amount": net,
                "items": [{"name": "Agreed fee", "amount": net, "frequency": "annual"}],
            }
        ]

    # Instalments are rounded to whole rupees so parents get clean figures;
    # the final row absorbs the remainder, keeping the total exact.
    if gross <= 0:
        share = float(int(net / len(installments)))
        for inst in installments[:-1]:
            inst["amount"] = share
        installments[-1]["amount"] = money(net - share * (len(installments) - 1))
        return installments

    factor = net / gross
    running = 0.0
    for inst in installments[:-1]:
        inst["amount"] = float(round(inst["amount"] * factor))
        running = money(running + inst["amount"])
    installments[-1]["amount"] = money(max(0.0, net - running))
    return installments


def build_fee_plan(
    components: list[dict[str, Any]],
    academic_year: str | None = None,
    agreed_total: float | None = None,
    discount: float = 0,
    discount_reason: str | None = None,
) -> dict[str, Any]:
    """Build a student's fee plan.

    ``agreed_total`` is what the admin actually settled on with the parents and
    always wins. When it is omitted the plan falls back to
    ``class total - discount``.
    """
    ay = academic_year or settings.academic_year
    items = [
        {
            "name": c.get("name", "Fee"),
            "amount": money(c.get("amount")),
            "frequency": c.get("frequency", "annual"),
        }
        for c in components
        if money(c.get("amount")) > 0
    ]
    installments = build_installments(items, ay)
    gross = money(sum(i["amount"] for i in installments))

    if agreed_total is not None:
        net = money(max(0.0, agreed_total))
    else:
        net = money(max(0.0, gross - money(discount)))

    installments = scale_installments(installments, gross, net, ay)

    return {
        "academic_year": ay,
        "items": items,
        "installments": installments,
        "gross": gross,
        "agreed_total": net,
        # Exactly one of these is non-zero: a concession off the standard fee,
        # or an agreed amount above it.
        "discount": money(max(0.0, gross - net)),
        "extra": money(max(0.0, net - gross)),
        "discount_reason": discount_reason,
        "net_payable": net,
        "generated_at": now_utc(),
    }


def allocate(
    installments: list[dict[str, Any]], amount_paid: float, today: date | None = None
) -> list[dict[str, Any]]:
    """Spread ``amount_paid`` across the schedule, earliest due date first."""
    today = today or date.today()
    left = money(amount_paid)
    rows = []

    for inst in installments:
        due_amount = money(inst.get("amount"))
        paid = money(min(left, due_amount))
        left = money(left - paid)
        balance = money(due_amount - paid)
        due_date = inst.get("due_date")
        if hasattr(due_date, "date"):  # datetime coming back from Mongo
            due_date = due_date.date()

        if balance <= 0.004:
            status = "paid"
        elif due_date and due_date < today:
            status = "overdue"
        elif paid > 0:
            status = "partial"
        else:
            status = "due"

        rows.append(
            {
                "label": inst.get("label", ""),
                "due_date": due_date,
                "amount": due_amount,
                "items": inst.get("items", []),
                "paid": paid,
                "balance": balance,
                "status": status,
            }
        )
    return rows


def auto_allocate_items(
    installments: list[dict[str, Any]], already_paid: float, new_amount: float
) -> list[dict[str, Any]]:
    """Describe what a new payment is being collected *towards*."""
    rows = allocate(installments, already_paid)
    left = money(new_amount)
    items: list[dict[str, Any]] = []

    for row in rows:
        if left <= 0:
            break
        if row["balance"] <= 0:
            continue
        take = money(min(left, row["balance"]))
        left = money(left - take)
        names = ", ".join(dict.fromkeys(i.get("name", "Fee") for i in row["items"]))
        label = f"{row['label']} - {names}" if names else row["label"]
        items.append({"name": label[:120], "amount": take})

    if left > 0:
        items.append({"name": "Advance / Other", "amount": left})
    return items


def summarise(fee_plan: dict[str, Any] | None, total_paid: float) -> dict[str, Any]:
    """Ledger totals for a student."""
    plan = fee_plan or {}
    installments = plan.get("installments", [])
    net = money(plan.get("net_payable", 0))
    paid = money(total_paid)
    rows = allocate(installments, paid)
    next_due = next((r for r in rows if r["balance"] > 0), None)

    return {
        "academic_year": plan.get("academic_year", settings.academic_year),
        "gross": money(plan.get("gross", 0)),
        "discount": money(plan.get("discount", 0)),
        "extra": money(plan.get("extra", 0)),
        "net_payable": net,
        "total_paid": paid,
        "balance": money(net - paid),
        "installments": rows,
        "next_due": next_due,
        "overdue_amount": money(sum(r["balance"] for r in rows if r["status"] == "overdue")),
    }
