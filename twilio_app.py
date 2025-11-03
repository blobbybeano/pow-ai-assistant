"""Twilio webhook + REST API backing the PowWash WhatsApp workspace."""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Set

from flask import Flask, Response, abort, jsonify, request
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

from auto_responder import generate_reply
from conversation_store import conversation_store
from twilio_helpers import TwilioMessenger

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

PRICE_LIST_PATH = Path("price_list.json")
TONE_PROFILE_PATH = Path("tone_profile.md")

twilio_messenger = TwilioMessenger.from_env()
if not twilio_messenger:
    logging.warning(
        "Twilio credentials not detected. Manual outbound replies from the Flutter app will be disabled."
    )

AI_AUTOREPLY_DELAY_SECONDS = 180

_scheduled_message_ids: Set[str] = set()


def _build_reply(inbound_text: str) -> str:
    """Generate a PowWash response for the inbound WhatsApp message."""
    if not inbound_text:
        return (
            "Hi there! This is PowWash. I didn't catch your message—"
            "could you please resend it so we can prepare your quote?"
        )

    return generate_reply(
        message=inbound_text,
        price_list_path=PRICE_LIST_PATH,
        tone_profile_path=TONE_PROFILE_PATH,
        model="gpt-4o-mini",
        temperature=0.5,
    )


def _normalize_msisdn(raw: str) -> str:
    """Return a phone number in E.164 format if possible."""

    value = (raw or "").strip()
    if not value:
        return ""

    if value.lower().startswith("whatsapp:"):
        value = value.split(":", 1)[1]

    value = value.replace(" ", "")

    if value.startswith("+"):
        digits = "+" + re.sub(r"[^\d]", "", value[1:])
        return digits if digits != "+" else ""

    if value.startswith("00"):
        digits = re.sub(r"[^\d]", "", value[2:])
        return f"+{digits}" if digits else ""

    digits = re.sub(r"[^\d]", "", value)
    if not digits:
        return ""

    return f"+{digits}"


def _conversation_id(from_number: str, wa_id: str | None = None) -> str:
    """Normalise Twilio's sender identifiers into a stable conversation id."""

    for candidate in (from_number, wa_id):
        normalized = _normalize_msisdn(candidate or "")
        if normalized:
            return normalized

    fallback = (wa_id or from_number or "").strip()
    if fallback.lower().startswith("whatsapp:"):
        fallback = fallback.split(":", 1)[1]
    return fallback or "unknown"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _schedule_ai_delivery(
    conversation_id: str,
    message_id: str,
    body: str,
    *,
    scheduled_for: datetime,
) -> None:
    if message_id in _scheduled_message_ids:
        return

    delay = max(0.0, (scheduled_for - datetime.now(timezone.utc)).total_seconds())

    def _deliver() -> None:
        message_snapshot = conversation_store.get_message(conversation_id, message_id)
        if not message_snapshot or message_snapshot.status != "scheduled":
            _scheduled_message_ids.discard(message_id)
            return

        if not twilio_messenger:
            logging.warning(
                "Twilio credentials missing; marking AI reply as failed for %s",
                conversation_id,
            )
            conversation_store.update_message(
                conversation_id,
                message_id,
                status="failed",
                sent_at=_iso_now(),
                error="Twilio credentials are not configured for outbound messaging",
            )
            _scheduled_message_ids.discard(message_id)
            return

        try:
            sid = twilio_messenger.send_whatsapp_message(to=conversation_id, body=body)
        except Exception as exc:  # pragma: no cover - network call
            logging.exception("Failed to send scheduled AI reply via Twilio")
            conversation_store.update_message(
                conversation_id,
                message_id,
                status="failed",
                sent_at=_iso_now(),
                error=str(exc),
            )
        else:
            conversation_store.update_message(
                conversation_id,
                message_id,
                status="sent",
                sent_at=_iso_now(),
                transport_sid=sid,
            )
        finally:
            _scheduled_message_ids.discard(message_id)

    timer = threading.Timer(delay, _deliver)
    timer.daemon = True
    timer.start()
    _scheduled_message_ids.add(message_id)


def _bootstrap_pending_messages() -> None:
    for conversation_id, message in conversation_store.pending_scheduled_messages():
        if message.scheduled_send_at:
            try:
                scheduled_for = datetime.fromisoformat(message.scheduled_send_at)
            except ValueError:
                scheduled_for = datetime.now(timezone.utc) + timedelta(
                    seconds=AI_AUTOREPLY_DELAY_SECONDS
                )
        else:
            scheduled_for = datetime.now(timezone.utc) + timedelta(
                seconds=AI_AUTOREPLY_DELAY_SECONDS
            )
            conversation_store.update_message(
                conversation_id,
                message.id,
                status="scheduled",
                sent_at=None,
                scheduled_send_at=scheduled_for.isoformat(),
            )
        _schedule_ai_delivery(
            conversation_id,
            message.id,
            message.text,
            scheduled_for=scheduled_for,
        )


# Kick off any AI replies that were awaiting delivery when the server restarts.
_bootstrap_pending_messages()


@app.post("/twilio/whatsapp")
def whatsapp_webhook() -> Response:
    """Return a TwiML response and update the conversation store."""

    inbound_text = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")
    profile_name = request.form.get("ProfileName") or request.form.get("WaId")
    profile_photo_url = request.form.get("ProfilePictureUrl") or request.form.get(
        "ProfileImageUrl"
    )

    wa_id = request.form.get("WaId")
    conversation_id = _conversation_id(from_number, wa_id)

    conversation_store.record_message(
        conversation_id,
        text=inbound_text,
        author="customer",
        direction="inbound",
        profile_name=profile_name,
        profile_photo_url=profile_photo_url,
        increment_unread=True,
    )

    if conversation_store.default_responder_id:
        conversation_store.assign_conversation(
            conversation_id, conversation_store.default_responder_id
        )

    conversation_snapshot = conversation_store.get_conversation(conversation_id)
    ai_enabled = conversation_snapshot["aiEnabled"] if conversation_snapshot else True

    response = MessagingResponse()

    if ai_enabled:
        drafting_message = conversation_store.record_message(
            conversation_id,
            text="",
            author="ai",
            direction="outbound",
            status="drafting",
        )

        try:
            reply_text = _build_reply(inbound_text)
        except Exception as exc:  # pragma: no cover - network call
            logging.exception("Failed to build AI reply")
            conversation_store.update_message(
                conversation_id,
                drafting_message.id,
                status="failed",
                error=str(exc),
            )
            return Response(str(response), mimetype="application/xml")

        send_after = datetime.now(timezone.utc) + timedelta(
            seconds=AI_AUTOREPLY_DELAY_SECONDS
        )
        conversation_store.update_message(
            conversation_id,
            drafting_message.id,
            text=reply_text,
            status="scheduled",
            scheduled_send_at=send_after.isoformat(),
        )
        _schedule_ai_delivery(
            conversation_id,
            drafting_message.id,
            reply_text,
            scheduled_for=send_after,
        )
    else:
        logging.info(
            "AI disabled for conversation %s; awaiting manual follow-up",
            conversation_id,
        )

    return Response(str(response), mimetype="application/xml")


# ---------------------------------------------------------------------------
# REST API powering the Flutter workspace
# ---------------------------------------------------------------------------


@app.get("/api/health")
def healthcheck() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/settings/responder")
def api_get_default_responder() -> Response:
    return jsonify({"defaultResponderId": conversation_store.default_responder_id})


@app.post("/api/settings/responder")
def api_set_default_responder() -> Response:
    payload = request.get_json(silent=True) or {}
    responder_id = payload.get("responderId")
    if responder_id is not None and not isinstance(responder_id, str):
        abort(400, description="responderId must be a string")
    conversation_store.set_default_responder(responder_id)
    return jsonify({"defaultResponderId": conversation_store.default_responder_id})


@app.get("/api/conversations")
def api_list_conversations() -> Response:
    conversations = conversation_store.list_conversations()
    return jsonify({"conversations": conversations})


@app.get("/api/conversations/<conversation_id>")
def api_get_conversation(conversation_id: str) -> Response:
    convo = conversation_store.get_conversation(conversation_id, mark_read=True)
    if convo is None:
        abort(404, description="Conversation not found")
    return jsonify(convo)


@app.post("/api/conversations/<conversation_id>/toggle-ai")
def api_toggle_ai(conversation_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    enabled = bool(payload.get("enabled", True))
    responder_id = payload.get("responderId")
    if responder_id:
        conversation_store.assign_conversation(conversation_id, responder_id)
    result = conversation_store.set_ai_enabled(conversation_id, enabled)
    return jsonify({"enabled": result})


@app.post("/api/conversations/<conversation_id>/messages")
def api_send_manual_message(conversation_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()

    if not text:
        abort(400, description="Message text is required")

    if not twilio_messenger:
        abort(
            500,
            description="Twilio credentials are not configured for outbound messaging",
        )

    try:
        sid = twilio_messenger.send_whatsapp_message(to=conversation_id, body=text)
    except Exception as exc:  # pragma: no cover - network call
        logging.exception("Failed to send manual reply via Twilio")
        abort(502, description=str(exc))

    message = conversation_store.record_message(
        conversation_id,
        text=text,
        author="agent",
        direction="outbound",
        transport_sid=sid,
        sent_at=_iso_now(),
    )

    return jsonify({"status": "sent", "sid": sid, "message": message.to_dict()})


@app.post("/api/conversations/<conversation_id>/messages/<message_id>/cancel")
def api_cancel_ai_message(conversation_id: str, message_id: str) -> Response:
    message = conversation_store.cancel_scheduled_message(conversation_id, message_id)
    if message is None:
        abort(404, description="Scheduled AI message not found")

    _scheduled_message_ids.discard(message_id)
    return jsonify({"status": "cancelled", "message": message.to_dict()})


@app.post("/api/conversations/<conversation_id>/ai-draft")
def api_generate_ai_draft(conversation_id: str) -> Response:
    convo = conversation_store.get_conversation(conversation_id)
    if convo is None:
        abort(404, description="Conversation not found")

    latest = conversation_store.latest_customer_message(conversation_id)
    if latest is None:
        abort(400, description="No customer message available for drafting")

    draft = _build_reply(latest.text)

    return jsonify({"draft": draft, "model": "gpt-4o-mini"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
