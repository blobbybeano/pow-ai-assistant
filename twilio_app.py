"""Twilio webhook + REST API backing the PowWash WhatsApp workspace."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

from flask import Flask, Response, abort, jsonify, request
from twilio.twiml.messaging_response import MessagingResponse

from auto_responder import generate_reply
from conversation_store import conversation_store
from twilio_helpers import TwilioMessenger

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

PRICE_LIST_PATH = Path("price_list.json")
TONE_PROFILE_PATH = Path("tone_profile.md")

twilio_messenger = TwilioMessenger.from_env()
if not twilio_messenger:
    logging.warning(
        "Twilio credentials not detected. Manual outbound replies from the Flutter app will be disabled."
    )

ACK_MESSAGE = "Thanks for reaching out! A PowWash specialist will reply shortly."


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


def _conversation_id(from_number: str) -> str:
    return from_number.replace("whatsapp:", "")


@app.post("/twilio/whatsapp")
def whatsapp_webhook() -> Response:
    """Return a TwiML response and update the conversation store."""

    inbound_text = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")
    profile_name = request.form.get("ProfileName") or request.form.get("WaId")

    conversation_id = _conversation_id(from_number)

    conversation_store.record_message(
        conversation_id,
        text=inbound_text,
        author="customer",
        direction="inbound",
        profile_name=profile_name,
        increment_unread=True,
    )

    conversation_snapshot = conversation_store.get_conversation(conversation_id)
    ai_enabled = conversation_snapshot["aiEnabled"] if conversation_snapshot else True

    response = MessagingResponse()

    if ai_enabled:
        reply_text = _build_reply(inbound_text)
        conversation_store.record_message(
            conversation_id,
            text=reply_text,
            author="ai",
            direction="outbound",
        )
        response.message(reply_text)
    else:
        response.message(ACK_MESSAGE)
        conversation_store.record_message(
            conversation_id,
            text=ACK_MESSAGE,
            author="system",
            direction="outbound",
        )

    return Response(str(response), mimetype="application/xml")


# ---------------------------------------------------------------------------
# REST API powering the Flutter workspace
# ---------------------------------------------------------------------------


@app.get("/api/health")
def healthcheck() -> Dict[str, str]:
    return {"status": "ok"}


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
    result = conversation_store.set_ai_enabled(conversation_id, enabled)
    return jsonify({"enabled": result})


@app.post("/api/conversations/<conversation_id>/messages")
def api_send_manual_message(conversation_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()

    if not text:
        abort(400, description="Message text is required")

    if not twilio_messenger:
        abort(500, description="Twilio credentials are not configured for outbound messaging")

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
    )

    return jsonify({"status": "sent", "sid": sid, "message": message.to_dict()})


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
