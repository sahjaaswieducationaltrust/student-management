"""Sending parent messages through MSG91 — WhatsApp first, SMS as fallback.

Why this shape:

* WhatsApp utility templates are cheaper per message than Indian SMS and carry
  far more text, so they are tried first. SMS exists to catch the families the
  first attempt could not reach — a parent not on WhatsApp, or a template
  rejected at delivery — rather than as a price comparison per send.
* Both channels can only carry templates that were approved in advance: by Meta
  for WhatsApp, and on the DLT portal for SMS. Free-form text is not sendable,
  so the app's own wording is a *preview* and the provider template is what
  actually goes out.
* Nothing sends unless it is switched on twice — ``messaging_enabled`` and
  ``messaging_dry_run=false``. Every message costs money and reaches a real
  parent; a half-configured deployment must fail closed, not guess.

These payload shapes follow MSG91's v5 API. They have not been exercised
against a live account — that needs credentials and spends real money — so the
first run should be a dry run, then a single recipient, before any broadcast.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import settings

log = logging.getLogger("preschool.messaging")

TIMEOUT = httpx.Timeout(20.0, connect=10.0)


@dataclass
class SendResult:
    """What happened for one parent, on one channel."""

    ok: bool
    channel: str  # whatsapp | sms | none
    detail: str = ""
    provider_id: str | None = None
    dry_run: bool = False
    attempts: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "channel": self.channel,
            "detail": self.detail,
            "provider_id": self.provider_id,
            "dry_run": self.dry_run,
            "attempts": self.attempts,
        }


def channel_availability() -> dict[str, Any]:
    """What this deployment can actually do right now."""
    return {
        "enabled": settings.messaging_enabled,
        "dry_run": settings.messaging_dry_run,
        "whatsapp_ready": settings.whatsapp_ready,
        "sms_ready": settings.sms_ready,
        "sms_fallback": settings.messaging_sms_fallback,
        # Click-to-chat stays the answer whenever automated sending cannot run.
        "click_to_chat": not (
            settings.messaging_enabled and (settings.whatsapp_ready or settings.sms_ready)
        ),
    }


async def _post(client: httpx.AsyncClient, path: str, payload: dict) -> tuple[bool, str, str | None]:
    """One provider call. Returns (ok, detail, provider_id)."""
    url = f"{settings.msg91_base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        response = await client.post(
            url,
            json=payload,
            headers={"authkey": settings.msg91_auth_key, "Content-Type": "application/json"},
        )
    except httpx.RequestError as exc:
        return False, f"network error: {exc.__class__.__name__}", None

    if response.status_code >= 400:
        # Provider errors are short and worth keeping verbatim — they name the
        # unapproved template or the unregistered header.
        return False, f"HTTP {response.status_code}: {response.text[:200]}", None

    try:
        body = response.json()
    except ValueError:
        return True, response.text[:200], None

    # MSG91 answers with {"type": "success"|"error", "message": ...}.
    if isinstance(body, dict) and str(body.get("type", "")).lower() == "error":
        return False, str(body.get("message"))[:200], None

    provider_id = None
    if isinstance(body, dict):
        provider_id = body.get("request_id") or body.get("messageId") or body.get("data")
    return True, "accepted by provider", str(provider_id) if provider_id else None


async def send_whatsapp(
    client: httpx.AsyncClient, to: str, template: str, variables: list[str], language: str = "en"
) -> tuple[bool, str, str | None]:
    payload = {
        "integrated_number": settings.msg91_whatsapp_number,
        "content_type": "template",
        "payload": {
            "messaging_product": "whatsapp",
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": language, "policy": "deterministic"},
                "to_and_components": [
                    {
                        "to": [to],
                        "components": {
                            f"body_{i + 1}": {"type": "text", "value": value}
                            for i, value in enumerate(variables)
                        },
                    }
                ],
            },
        },
    }
    return await _post(client, "v5/whatsapp/whatsapp-outbound-message/bulk/", payload)


async def send_sms(
    client: httpx.AsyncClient, to: str, variables: list[str]
) -> tuple[bool, str, str | None]:
    # DLT templates address their variables positionally as VAR1, VAR2, ...
    recipient = {"mobiles": to}
    recipient.update({f"VAR{i + 1}": value for i, value in enumerate(variables)})
    payload = {
        "template_id": settings.msg91_sms_flow_id,
        "sender": settings.msg91_sms_sender_id,
        "short_url": "0",
        "recipients": [recipient],
    }
    return await _post(client, "v5/flow/", payload)


async def send_to_one(
    client: httpx.AsyncClient | None,
    *,
    phone: str,
    variables: list[str],
    whatsapp_template: str,
    preview: str = "",
) -> SendResult:
    """Deliver to one parent: WhatsApp, then SMS if that did not land."""
    if not settings.messaging_enabled:
        return SendResult(False, "none", "Automated sending is switched off")
    if not phone:
        return SendResult(False, "none", "No usable phone number")

    if settings.messaging_dry_run:
        log.info("[dry run] would message %s via %s: %s", phone, whatsapp_template, preview[:120])
        return SendResult(
            True, "whatsapp", "Dry run — nothing was sent", dry_run=True,
            attempts=[{"channel": "whatsapp", "ok": True, "detail": "dry run"}],
        )

    assert client is not None, "an HTTP client is required once dry run is off"
    attempts: list[dict[str, Any]] = []

    if settings.whatsapp_ready and whatsapp_template:
        ok, detail, provider_id = await send_whatsapp(client, phone, whatsapp_template, variables)
        attempts.append({"channel": "whatsapp", "ok": ok, "detail": detail})
        if ok:
            return SendResult(True, "whatsapp", detail, provider_id, attempts=attempts)

    if settings.messaging_sms_fallback and settings.sms_ready:
        ok, detail, provider_id = await send_sms(client, phone, variables)
        attempts.append({"channel": "sms", "ok": ok, "detail": detail})
        if ok:
            return SendResult(True, "sms", detail, provider_id, attempts=attempts)

    if not attempts:
        return SendResult(False, "none", "No channel is configured", attempts=attempts)
    return SendResult(False, attempts[-1]["channel"], attempts[-1]["detail"], attempts=attempts)


async def send_many(recipients: list[dict[str, Any]], whatsapp_template: str) -> list[dict[str, Any]]:
    """Send to a whole broadcast. Returns one result row per recipient.

    Sent a few at a time rather than all at once: providers rate-limit, and a
    burst that trips the limit would fail families for a reason that has
    nothing to do with their number.
    """
    results: list[dict[str, Any]] = []
    if settings.messaging_dry_run or not settings.messaging_enabled:
        for r in recipients:
            outcome = await send_to_one(
                None, phone=r.get("whatsapp") or "", variables=r.get("variables") or [],
                whatsapp_template=whatsapp_template, preview=r.get("message", ""),
            )
            results.append({"student_id": r.get("student_id"), **outcome.as_dict()})
        return results

    semaphore = asyncio.Semaphore(5)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async def one(r: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                outcome = await send_to_one(
                    client, phone=r.get("whatsapp") or "",
                    variables=r.get("variables") or [],
                    whatsapp_template=whatsapp_template, preview=r.get("message", ""),
                )
                return {"student_id": r.get("student_id"), **outcome.as_dict()}

        results = list(await asyncio.gather(*(one(r) for r in recipients)))

    return results
