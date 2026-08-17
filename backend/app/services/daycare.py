"""Daycare pricing.

Daycare is an add-on, not a class. A child in Nursery can also stay for
daycare, and a child from another school can take daycare alone — so it hangs
off the student record rather than the single classroom they belong to.

The charge is per hour of daily stay, per month: three hours a day for a
three-year-old is 3 x 700 = 2100 every month. Younger children need closer
minding, so the hourly rate is higher below the age threshold.
"""

from datetime import date, datetime
from typing import Any

from ..config import settings
from ..utils import age_from_dob, money


def rate_for_age(age_years: float | None) -> float:
    """The hourly monthly rate a child of this age qualifies for."""
    if age_years is None:
        # No date of birth on file: charge the higher rate rather than the
        # lower one, so a missing record never silently undercharges.
        return money(settings.daycare_rate_under)
    if age_years < settings.daycare_age_threshold:
        return money(settings.daycare_rate_under)
    return money(settings.daycare_rate_over)


def rate_for_dob(dob: date | datetime | None) -> float:
    return rate_for_age(age_from_dob(dob))


def monthly_fee(hours_per_day: float, rate_per_hour: float) -> float:
    return money(max(0.0, hours_per_day) * max(0.0, rate_per_hour))


def build_enrolment(
    hours_per_day: float,
    dob: date | datetime | None,
    rate_per_hour: float | None = None,
    started_on: date | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """The daycare block stored on a student.

    ``rate_per_hour`` is resolved from the child's age when it is not given and
    then *kept*. A child who turns three mid-year does not silently get cheaper
    — the fee a parent agreed to should not move on its own — but the profile
    reports that they now qualify for the lower band so it can be dropped at
    the next review.
    """
    resolved = money(rate_per_hour) if rate_per_hour is not None else rate_for_dob(dob)
    hours = max(0.0, min(float(hours_per_day or 0), settings.daycare_max_hours))
    return {
        "enrolled": hours > 0,
        "hours_per_day": hours,
        "rate_per_hour": resolved,
        "monthly_fee": monthly_fee(hours, resolved),
        "started_on": started_on,
        "note": note,
    }


def fee_component(daycare: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Daycare as a fee component, ready to join the rest of the plan.

    Monthly, so it spreads across the year's instalments instead of landing as
    one lump — which is how the parent actually pays it.
    """
    if not daycare or not daycare.get("enrolled"):
        return []
    fee = money(daycare.get("monthly_fee"))
    if fee <= 0:
        return []
    hours = daycare.get("hours_per_day") or 0
    label = f"Daycare ({_hours_label(hours)}/day)"
    return [{"name": label, "amount": fee, "frequency": "monthly"}]


def _hours_label(hours: float) -> str:
    """"3 hrs", not "3.0 hrs"; half hours survive as "2.5 hrs"."""
    value = int(hours) if float(hours).is_integer() else hours
    return f"{value} hr" if value == 1 else f"{value} hrs"


def eligibility_note(daycare: dict[str, Any] | None, dob: date | datetime | None) -> str | None:
    """Flag when a child has aged into the cheaper band but is still on the old rate."""
    if not daycare or not daycare.get("enrolled"):
        return None
    age = age_from_dob(dob)
    if age is None:
        return None
    current = money(daycare.get("rate_per_hour"))
    qualifies = rate_for_age(age)
    if qualifies < current:
        return (
            f"Now {settings.daycare_age_threshold}+ — qualifies for "
            f"{qualifies:.0f}/hr instead of {current:.0f}/hr"
        )
    return None
