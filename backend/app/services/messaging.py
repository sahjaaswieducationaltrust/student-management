"""Parent broadcasts — recipient lists and message templating.

No message is sent from the server. The WhatsApp Business API needs Meta
verification, a dedicated number and pre-approved templates, and Indian SMS
needs DLT registration; neither is in place. What the app does instead is
prepare the message per family and hand the staff member a click-to-chat link,
which sends from the school's own WhatsApp at no cost and with no approvals.

The templating and recipient logic lives here rather than in the router so a
real sending backend can reuse it unchanged if one is added later.
"""

from typing import Any

from ..config import settings

# {child}, {parent}, {class}, {school} and {admission_no} are filled per family.
TEMPLATES: list[dict[str, str]] = [
    {
        "key": "holiday",
        "label": "Holiday notice",
        "body": (
            "Dear Parent of {child},\n\n"
            "{school} will remain closed on <date> for <occasion>. "
            "Classes resume as usual the next working day.\n\n"
            "Thank you,\n{school}"
        ),
    },
    {
        "key": "event",
        "label": "Event invitation",
        "body": (
            "Dear Parent of {child},\n\n"
            "We are delighted to invite you to <event> on <date> at <time> "
            "at {school}. We look forward to celebrating with you and {child}.\n\n"
            "Warm regards,\n{school}"
        ),
    },
    {
        "key": "ptm",
        "label": "Parent-teacher meeting",
        "body": (
            "Dear Parent of {child},\n\n"
            "The parent-teacher meeting for {class} is on <date> between "
            "<time>. Please do come and meet {child}'s teacher.\n\n"
            "Regards,\n{school}"
        ),
    },
    {
        "key": "fee_reminder",
        "label": "Fee reminder",
        "body": (
            "Dear Parent of {child},\n\n"
            "This is a gentle reminder that the fee instalment for {child} "
            "({admission_no}) is due. Kindly arrange payment at your "
            "convenience.\n\n"
            "Thank you,\n{school}"
        ),
    },
    {
        "key": "closure",
        "label": "Unplanned closure",
        "body": (
            "Dear Parent of {child},\n\n"
            "Due to <reason>, {school} will be closed today. "
            "We are sorry for the short notice.\n\n"
            "{school}"
        ),
    },
    {
        "key": "blank",
        "label": "Write my own",
        "body": "Dear Parent of {child},\n\n\n\n{school}",
    },
]


def school_label() -> str:
    """How the school signs itself in a message."""
    return settings.school_full_name


def render(body: str, recipient: dict[str, Any]) -> str:
    """Fill the per-family placeholders. Unknown ones are left alone.

    Angle-bracket blanks like <date> are intentionally NOT substituted — they
    are prompts for the person writing the message, and leaving them visible
    means an unfilled one is obvious before it is sent rather than after.
    """
    values = {
        "child": recipient.get("child_name") or "your child",
        "parent": recipient.get("guardian_name") or "Parent",
        "class": recipient.get("classroom_name") or "the class",
        "school": school_label(),
        "admission_no": recipient.get("admission_no") or "",
    }
    out = body
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def to_variables(rendered: str, recipient: dict[str, Any]) -> list[str]:
    """Positional variables for the approved provider template.

    Both channels can only send templates cleared in advance — by Meta for
    WhatsApp, on the DLT portal for SMS — so the notice the school types cannot
    go out as-is. It travels instead as the second variable of a template
    shaped "Dear Parent of {{1}}, {{2}}", which is what lets the wording change
    without a fresh approval each time.

    The salutation and sign-off belong to the approved template, so they are
    stripped from the body here rather than being sent twice.
    """
    child = recipient.get("child_name") or "your child"
    lines = [line.strip() for line in rendered.splitlines()]
    school = school_label()

    kept = [
        line for line in lines
        if line
        and not line.lower().startswith("dear parent")
        and line.rstrip(",") != school
        and line.rstrip(",").lower() not in {"thank you", "regards", "warm regards"}
    ]
    return [child, " ".join(kept).strip() or rendered.strip()]


def unfilled_blanks(body: str) -> list[str]:
    """The <...> prompts still sitting in a message."""
    import re

    return sorted(set(re.findall(r"<[^<>\n]{1,40}>", body)))
