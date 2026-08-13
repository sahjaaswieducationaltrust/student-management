"""Parent broadcasts: build the recipient list, keep a record of what went out.

Nothing is sent from here — see services/messaging.py for why. The endpoints
prepare per-family messages for click-to-chat and log what staff actually sent,
so "did the parents get told about the holiday?" has an answer.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import settings
from ..deps import CurrentUser, DbDep, get_current_user, require_roles
from ..schemas import (
    BroadcastCreate,
    BroadcastOut,
    MessageTemplate,
    MessagingStatus,
    RecipientsResponse,
    SendRequest,
)
from ..services.fees import summarise
from ..services.messaging import TEMPLATES, render, to_variables, unfilled_blanks
from ..services.payments import paid_totals
from ..services.senders import channel_availability, send_many
from ..utils import normalise_phone, now_utc, person_name, serialize, to_object_id

router = APIRouter(
    prefix="/api/messages", tags=["messages"], dependencies=[Depends(get_current_user)]
)

ManageOnly = Depends(require_roles("admin", "staff"))


@router.get("/templates", response_model=list[MessageTemplate])
async def list_templates():
    return TEMPLATES


@router.get("/status", response_model=MessagingStatus)
async def messaging_status():
    """Whether this deployment can send by itself, so the UI stops guessing."""
    return {
        **channel_availability(),
        "whatsapp_template": settings.msg91_whatsapp_template or None,
    }


@router.post("/send", response_model=BroadcastOut, dependencies=[ManageOnly])
async def send_now(payload: SendRequest, db: DbDep, user: CurrentUser):
    """Send an announcement to every matching family, and record the outcome.

    Refuses rather than half-works: an unfilled <date> would go out verbatim to
    every parent, and a deployment with no provider configured would report
    success for messages nobody received.
    """
    blanks = unfilled_blanks(payload.body)
    if blanks:
        raise HTTPException(
            status_code=400,
            detail=f"Fill in {', '.join(blanks)} before sending — it would go out as written.",
        )

    availability = channel_availability()
    if not availability["enabled"]:
        raise HTTPException(
            status_code=409,
            detail="Automated sending is switched off. Set MESSAGING_ENABLED=true once the "
                   "MSG91 account, DLT registration and approved templates are in place.",
        )
    if not (availability["whatsapp_ready"] or availability["sms_ready"]):
        raise HTTPException(
            status_code=409,
            detail="No channel is configured. Add the MSG91 credentials for WhatsApp or SMS.",
        )

    prepared = await _recipient_rows(db, payload.body, payload.classroom_id, payload.dues_only)
    reachable = [r for r in prepared if r["whatsapp"]]
    if not reachable:
        raise HTTPException(
            status_code=400,
            detail="No family in this selection has a usable phone number.",
        )

    template = payload.whatsapp_template or settings.msg91_whatsapp_template
    for row in reachable:
        row["variables"] = to_variables(row["message"], row)

    outcomes = {o["student_id"]: o for o in await send_many(reachable, template)}

    recipients = []
    for row in prepared:
        outcome = outcomes.get(row["student_id"])
        if outcome is None:
            recipients.append({
                "student_id": row["student_id"], "child_name": row["child_name"],
                "whatsapp": None, "sent": False, "status": "skipped",
                "detail": "No usable phone number", "dry_run": False,
            })
            continue
        recipients.append({
            "student_id": row["student_id"], "child_name": row["child_name"],
            "whatsapp": row["whatsapp"], "sent": bool(outcome["ok"]),
            "status": "sent" if outcome["ok"] else "failed",
            "channel": outcome["channel"], "detail": outcome["detail"],
            "provider_id": outcome["provider_id"], "dry_run": outcome["dry_run"],
        })

    doc = {
        "title": payload.title.strip(),
        "body": payload.body,
        "channel": "auto",
        "whatsapp_template": template,
        "recipients": recipients,
        "created_by": user.get("name"),
        "created_by_id": user.get("id"),
        "created_at": now_utc(),
    }
    result = await db.broadcasts.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _shape(doc)


@router.get("/recipients", response_model=RecipientsResponse)
async def recipients(
    db: DbDep,
    body: str = Query(default="", max_length=2000, description="Message to render per family"),
    classroom_id: str | None = None,
    dues_only: bool = False,
):
    """Guardians to contact, each with the message already filled in for them."""
    rows = await _recipient_rows(db, body, classroom_id, dues_only)
    reachable = sum(1 for r in rows if r["whatsapp"])
    return {
        "recipients": rows,
        "total": len(rows),
        "reachable": reachable,
        "unreachable": len(rows) - reachable,
        "blanks": unfilled_blanks(body) if body else [],
    }


async def _recipient_rows(
    db, body: str, classroom_id: str | None, dues_only: bool
) -> list[dict]:
    """The families to contact. Shared so previewing and sending cannot diverge."""
    query: dict = {"status": "active"}
    if classroom_id:
        query["classroom_id"] = classroom_id

    students = await db.students.find(query).sort("first_name", 1).to_list(1000)
    class_names = {
        str(c["_id"]): c["name"] for c in await db.classrooms.find({}, {"name": 1}).to_list(200)
    }
    paid_map = await paid_totals(db, [str(s["_id"]) for s in students])

    rows = []
    for student in students:
        sid = str(student["_id"])
        summary = summarise(
            student.get("fee_plan"), paid_map.get(sid, 0.0), student.get("next_due_override")
        )
        if dues_only and summary["balance"] <= 0.01:
            continue

        guardian = student.get("guardian") or {}
        phone = guardian.get("primary_phone")
        whatsapp = normalise_phone(phone, settings.phone_country_code)
        # Fall back to the alternate number when the primary is unusable, so a
        # family with one good number between two fields still gets the message.
        if whatsapp is None:
            alternate = normalise_phone(
                guardian.get("alternate_phone"), settings.phone_country_code
            )
            if alternate:
                phone, whatsapp = guardian.get("alternate_phone"), alternate

        row = {
            "student_id": sid,
            "child_name": person_name(student.get("first_name"), student.get("last_name")),
            "admission_no": student.get("admission_no", ""),
            "classroom_name": class_names.get(student.get("classroom_id") or ""),
            "guardian_name": person_name(
                guardian.get("father_name") or guardian.get("mother_name")
                or guardian.get("guardian_name")
            )
            or None,
            "phone": phone,
            "whatsapp": whatsapp,
            "balance": summary["balance"],
        }
        row["message"] = render(body, row) if body else ""
        rows.append(row)

    return rows


@router.post("/broadcasts", response_model=BroadcastOut,
             status_code=status.HTTP_201_CREATED, dependencies=[ManageOnly])
async def create_broadcast(payload: BroadcastCreate, db: DbDep, user: CurrentUser):
    """Record a broadcast as staff begin sending it."""
    doc = {
        "title": payload.title.strip(),
        "body": payload.body,
        "channel": payload.channel,
        "recipients": [r.model_dump() for r in payload.recipients],
        "created_by": user.get("name"),
        "created_by_id": user.get("id"),
        "created_at": now_utc(),
    }
    result = await db.broadcasts.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _shape(doc)


@router.post("/broadcasts/{broadcast_id}/sent/{student_id}", response_model=BroadcastOut,
             dependencies=[ManageOnly])
async def mark_sent(broadcast_id: str, student_id: str, db: DbDep):
    """Tick one family off the list once their chat has been opened."""
    doc = await db.broadcasts.find_one_and_update(
        {"_id": to_object_id(broadcast_id, "broadcast id"), "recipients.student_id": student_id},
        {"$set": {"recipients.$.sent": True, "updated_at": now_utc()}},
        return_document=True,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Broadcast or recipient not found")
    return _shape(doc)


@router.get("/broadcasts", response_model=list[BroadcastOut])
async def list_broadcasts(db: DbDep, limit: int = Query(default=25, ge=1, le=200)):
    docs = await db.broadcasts.find({}).sort("created_at", -1).to_list(limit)
    return [_shape(d) for d in docs]


@router.delete("/broadcasts/{broadcast_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_roles("admin"))])
async def delete_broadcast(broadcast_id: str, db: DbDep):
    result = await db.broadcasts.delete_one(
        {"_id": to_object_id(broadcast_id, "broadcast id")}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Broadcast not found")


def _shape(doc: dict) -> dict:
    out = serialize(doc)
    recipients = out.get("recipients") or []
    out["total"] = len(recipients)
    out["sent_count"] = sum(1 for r in recipients if r.get("sent"))
    return out
