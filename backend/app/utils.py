import re
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

# Letters only — leaves dots, hyphens and apostrophes alone so "k.r. d'souza"
# becomes "K.R. D'Souza" rather than losing its punctuation.
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def title_name(value: str | None) -> str:
    """Proper-case a person's name: "jaaswika govindu" -> "Jaaswika Govindu".

    Names get typed in at the admission desk in whatever case the moment
    allows, and they end up on receipts parents keep. Normalising on the way
    in and on the way out means the register reads the same however it was
    entered. Names with an internal capital ("McDonald") come back as
    "Mcdonald" — rare enough here to be worth the trade for consistency.
    """
    if not value:
        return ""
    return _WORD.sub(lambda m: m.group(0).capitalize(), value.strip().lower())


def person_name(*parts: str | None) -> str:
    """Join and proper-case the pieces of a person's name."""
    return " ".join(filter(None, (title_name(p) for p in parts)))


def name_sort_key(doc: dict[str, Any]) -> tuple[str, str]:
    """Order people by name the way a person reading the list expects.

    Case-folded deliberately. Mongo sorts strings by their bytes, which puts
    every capital ahead of every lowercase letter — one child entered as
    "aarav" would file after "Zara". Names are proper-cased on save now, so
    that is unlikely, but the register is decades long and one hurried entry
    should not push a child to the bottom of the roll.

    Sorted on the first name because that is what a preschool calls a child
    by, and because half these records carry the whole name in that field
    with no surname at all.
    """
    return (
        str(doc.get("first_name") or "").strip().lower(),
        str(doc.get("last_name") or "").strip().lower(),
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_object_id(value: str, field: str = "id") -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {field}: {value}"
        )


def serialize(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert a Mongo document into a JSON-friendly dict (``_id`` -> ``id``)."""
    if doc is None:
        return None
    out: dict[str, Any] = {}
    for key, value in doc.items():
        if key == "_id":
            out["id"] = str(value)
        elif isinstance(value, ObjectId):
            out[key] = str(value)
        elif isinstance(value, dict):
            out[key] = serialize(value)
        elif isinstance(value, list):
            out[key] = [
                serialize(v)
                if isinstance(v, dict)
                else (str(v) if isinstance(v, ObjectId) else v)
                for v in value
            ]
        else:
            out[key] = value
    return out


def encode_dates(value: Any) -> Any:
    """BSON has no ``date`` type — store plain dates as midnight UTC datetimes.

    Reading them back gives an exact-midnight datetime, which Pydantic coerces
    straight back into a ``date`` for the response models.
    """
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, dict):
        return {k: encode_dates(v) for k, v in value.items()}
    if isinstance(value, list):
        return [encode_dates(v) for v in value]
    return value


PAYMENT_MODE_LABELS = {
    "cash": "Cash",
    "upi": "UPI",
    "card": "Card",
    "cheque": "Cheque",
    "bank_transfer": "Bank Transfer",
}


def payment_mode_label(mode: str | None) -> str:
    """"upi" -> "UPI", not "Upi"."""
    key = str(mode or "cash")
    return PAYMENT_MODE_LABELS.get(key, key.replace("_", " ").title())


def money(value: float | int | None) -> float:
    """Normalise a monetary amount to 2 decimal places."""
    return round(float(value or 0), 2)


def age_from_dob(dob: date | datetime | None) -> float | None:
    if dob is None:
        return None
    if isinstance(dob, datetime):
        dob = dob.date()
    today = date.today()
    years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    months = (today.month - dob.month) % 12
    return round(years + months / 12, 1)


_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two_digits(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")


def _three_digits(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{_ONES[hundreds]} Hundred")
    if rest:
        parts.append(_two_digits(rest))
    return " ".join(parts)


def amount_in_words(amount: float, currency: str = "Rupees", subunit: str = "Paise") -> str:
    """Indian numbering system: crore / lakh / thousand."""
    amount = money(amount)
    whole = int(amount)
    fraction = int(round((amount - whole) * 100))

    if whole == 0:
        words = "Zero"
    else:
        crore, rest = divmod(whole, 10_000_000)
        lakh, rest = divmod(rest, 100_000)
        thousand, hundred = divmod(rest, 1000)
        chunks = []
        if crore:
            chunks.append(f"{_three_digits(crore)} Crore")
        if lakh:
            chunks.append(f"{_two_digits(lakh)} Lakh")
        if thousand:
            chunks.append(f"{_two_digits(thousand)} Thousand")
        if hundred:
            chunks.append(_three_digits(hundred))
        words = " ".join(chunks)

    text = f"{currency} {words}"
    if fraction:
        text += f" and {_two_digits(fraction)} {subunit}"
    return text + " Only"
