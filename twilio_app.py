"""Twilio webhook + REST API backing the PowWash WhatsApp workspace (production-safe)."""

from __future__ import annotations

import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Set
from uuid import uuid4

import requests
from flask import Flask, Response, abort, jsonify, request, send_from_directory
from flask_cors import CORS
from twilio.base.exceptions import TwilioRestException
from twilio.twiml.messaging_response import MessagingResponse

from auto_responder import generate_reply
from conversation_store import conversation_store
from twilio_helpers import TwilioMessenger

# -----------------------------------------------------------
# Setup
# -----------------------------------------------------------
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

PRICE_LIST_PATH = Path("price_list.json")
TONE_PROFILE_PATH = Path("tone_profile.md")
UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
_TWILIO_MEDIA_TIMEOUT_SECONDS = 20
_MEDIA_EXTENSION_MAP = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
}

AI_AUTOREPLY_DELAY_SECONDS = 180
_scheduled_message_ids: Set[str] = set()


# -----------------------------------------------------------
# Twilio Messenger dynamic builder
# -----------------------------------------------------------
def get_twilio_messenger() -> TwilioMessenger | None:
    """Always rebuild the TwilioMessenger from fresh environment variables."""
    messenger = TwilioMessenger.from_env()
    if messenger:
        cfg = messenger._config
        if cfg.messaging_service_sid:
            cfg.whatsapp_from = None
        return messenger

    logging.warning("⚠️ Twilio credentials not detected or invalid.")
    return None


# -----------------------------------------------------------
# Utility functions
# -----------------------------------------------------------
def _resolve_media_extension(media_url: str | None, content_type: str | None) -> str:
    """Resolve an appropriate file extension for inbound media."""
    if content_type:
        normalized = content_type.lower().strip()
        if normalized in _MEDIA_EXTENSION_MAP:
            return _MEDIA_EXTENSION_MAP[normalized]

    url_lower = (media_url or "").lower()
    if url_lower.endswith(".png"):
        return ".png"
    if url_lower.endswith(".jpeg") or url_lower.endswith(".jpg"):
        return ".jpg"
    return ".jpg"


def _download_whatsapp_media(media_url: str | None, content_type: str | None) -> Path | None:
    """Download an inbound WhatsApp media file via the Twilio REST API."""
    if not media_url:
        return None

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        logging.error("🚫 Cannot download media without Twilio credentials.")
        return None

    extension = _resolve_media_extension(media_url, content_type)
    filename = f"{uuid4().hex}{extension}"
    file_path = UPLOADS_DIR / filename

    try:
        response = requests.get(
            media_url,
            auth=(account_sid, auth_token),
            timeout=_TWILIO_MEDIA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logging.error("❌ Failed to download WhatsApp media from Twilio: %s", exc)
        return None

    try:
        file_path.write_bytes(response.content)
    except OSError as exc:
        logging.error("❌ Failed to persist inbound media %s: %s", filename, exc)
        return None

    logging.info("📸 Saved inbound WhatsApp media to %s", file_path)
    return file_path


def _collect_inbound_attachments(form) -> List[str]:
    """Download and persist inbound WhatsApp media attachments."""
    attachments: List[str] = []
    try:
        num_media = int(form.get("NumMedia", "0") or 0)
    except (TypeError, ValueError):
        num_media = 0

    if num_media <= 0:
        return attachments

    for index in range(num_media):
        media_url = form.get(f"MediaUrl{index}")
        if not media_url:
            continue
        content_type = form.get(f"MediaContentType{index}")
        file_path = _download_whatsapp_media(media_url, content_type)
        if not file_path:
            continue
        attachments.append(str(file_path))
        logging.info("📁 Stored local media path for AI processing: %s", file_path)

    return attachments


def _build_reply(inbound_text: str, attachments: List[str] | None = None) -> str:
    """Generate an AI PowWash reply for an inbound WhatsApp message."""
    sanitized_text = (inbound_text or "").strip()
    attachment_list = list(attachments or [])

    if not sanitized_text and not attachment_list:
        return (
            "Hi there! This is PowWash. I didn’t catch your message—"
            "could you please resend it so we can prepare your quote?"
        )

    if not sanitized_text:
        sanitized_text = (
            "The customer sent images without any accompanying text. "
            "Please review the attachments and respond helpfully."
        )

    return generate_reply(
        message=sanitized_text,
        price_list_path=PRICE_LIST_PATH,
        tone_profile_path=TONE_PROFILE_PATH,
        model="gpt-4o-mini",
        temperature=0.5,
        attachments=attachment_list,
    )


def _normalize_msisdn(raw: str) -> str:
    """Convert any phone-like input into proper E.164 (+44…) format."""
    value = (raw or "").strip()
    if not value:
        return ""

    if value.lower().startswith("whatsapp:"):
        value = value.split(":", 1)[1]

    value = re.sub(r"[^\d+]", "", value)

    if value.startswith("+"):
        digits = "+" + re.sub(r"[^\d]", "", value[1:])
    elif value.startswith("00"):
        digits = "+" + re.sub(r"[^\d]", "", value[2:])
    elif value.startswith("0"):
        digits = "+44" + value[1:]
    else:
        digits = "+" + re.sub(r"[^\d]", "", value)

    return digits if digits != "+" else ""


def _conversation_id(from_number: str, wa_id: str | None = None) -> str:
    """Normalize sender identifiers into a stable E.164 number (no whatsapp: prefix)."""
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


# -----------------------------------------------------------
# AI message scheduling logic
# -----------------------------------------------------------
def _schedule_ai_delivery(conversation_id: str, message_id: str, body: str, *, scheduled_for: datetime) -> None:
    """Schedules a delayed AI message to be sent to a WhatsApp user."""
    if message_id in _scheduled_message_ids:
        return

    delay = max(0.0, (scheduled_for - datetime.now(timezone.utc)).total_seconds())

    def _deliver() -> None:
        message_snapshot = conversation_store.get_message(conversation_id, message_id)
        if not message_snapshot or message_snapshot.status != "scheduled":
            _scheduled_message_ids.discard(message_id)
            return

        messenger = get_twilio_messenger()
        if not messenger:
            logging.error("🚫 Twilio credentials missing; cannot deliver AI reply.")
            conversation_store.update_message(
                conversation_id, message_id, status="failed", sent_at=_iso_now(),
                error="Twilio credentials not configured.",
            )
            _scheduled_message_ids.discard(message_id)
            return

        to_address = f"whatsapp:{conversation_id}"

        try:
            sid = messenger.send_whatsapp_message(to=to_address, body=body)
        except TwilioRestException as exc:
            logging.error(f"❌ Twilio error {exc.code} ({exc.status}): {exc.msg}")
            conversation_store.update_message(
                conversation_id, message_id, status="failed", sent_at=_iso_now(),
                error=f"Twilio error {exc.code}: {exc.msg}",
            )
        except Exception as exc:
            logging.exception("❌ Unexpected error sending AI reply via Twilio")
            conversation_store.update_message(
                conversation_id, message_id, status="failed", sent_at=_iso_now(), error=str(exc),
            )
        else:
            conversation_store.update_message(
                conversation_id, message_id, status="sent", sent_at=_iso_now(), transport_sid=sid,
            )
        finally:
            _scheduled_message_ids.discard(message_id)

    timer = threading.Timer(delay, _deliver)
    timer.daemon = True
    timer.start()
    _scheduled_message_ids.add(message_id)


def _bootstrap_pending_messages() -> None:
    """Re-arm any AI messages that were scheduled before server restart."""
    for conversation_id, message in conversation_store.pending_scheduled_messages():
        try:
            scheduled_for = (
                datetime.fromisoformat(message.scheduled_send_at)
                if message.scheduled_send_at
                else datetime.now(timezone.utc) + timedelta(seconds=AI_AUTOREPLY_DELAY_SECONDS)
            )
        except ValueError:
            scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=AI_AUTOREPLY_DELAY_SECONDS)

        conversation_store.update_message(
            conversation_id, message.id, status="scheduled", scheduled_send_at=scheduled_for.isoformat(),
        )
        _schedule_ai_delivery(conversation_id, message.id, message.text, scheduled_for=scheduled_for)


_bootstrap_pending_messages()


# -----------------------------------------------------------
# Twilio WhatsApp webhook
# -----------------------------------------------------------
@app.post("/twilio/whatsapp")
def whatsapp_webhook() -> Response:
    """Receives inbound WhatsApp messages from Twilio."""
    inbound_text = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")
    profile_name = request.form.get("ProfileName") or request.form.get("WaId")
    profile_photo_url = request.form.get("ProfilePictureUrl") or request.form.get("ProfileImageUrl")
    wa_id = request.form.get("WaId")
    conversation_id = _conversation_id(from_number, wa_id)
    attachments = _collect_inbound_attachments(request.form)

    conversation_store.record_message(
        conversation_id, text=inbound_text, author="customer", direction="inbound",
        profile_name=profile_name, profile_photo_url=profile_photo_url, increment_unread=True,
        attachments=attachments,
    )

    if conversation_store.default_responder_id:
        conversation_store.assign_conversation(conversation_id, conversation_store.default_responder_id)

    convo_snapshot = conversation_store.get_conversation(conversation_id)
    ai_enabled = convo_snapshot["aiEnabled"] if convo_snapshot else True
    response = MessagingResponse()

    if ai_enabled:
        drafting_message = conversation_store.record_message(
            conversation_id, text="", author="ai", direction="outbound", status="drafting",
        )
        try:
            reply_text = _build_reply(inbound_text, attachments)
        except Exception as exc:
            logging.exception("AI reply generation failed")
            conversation_store.update_message(conversation_id, drafting_message.id, status="failed", error=str(exc))
            return Response(str(response), mimetype="application/xml")

        send_after = datetime.now(timezone.utc) + timedelta(seconds=AI_AUTOREPLY_DELAY_SECONDS)
        conversation_store.update_message(
            conversation_id, drafting_message.id, text=reply_text,
            status="scheduled", scheduled_send_at=send_after.isoformat(),
        )
        _schedule_ai_delivery(conversation_id, drafting_message.id, reply_text, scheduled_for=send_after)
    else:
        logging.info("AI disabled for conversation %s; manual follow-up expected.", conversation_id)

    return Response(str(response), mimetype="application/xml")


# -----------------------------------------------------------
# REST API endpoints used by Flutter workspace
# -----------------------------------------------------------
@app.get("/api/health")
def healthcheck() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/uploads/<path:filename>")
def serve_uploaded_file(filename: str) -> Response:
    """Expose saved media files for downstream consumption (e.g. OpenAI)."""
    return send_from_directory(UPLOADS_DIR, filename)


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
    """Manual outbound message from agent in Flutter app."""
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    sender_id = payload.get("senderId")

    if not text:
        abort(400, description="Message text is required")

    status, sid, error_message = "sent", None, None
    delivery_via = "whatsapp"

    if sender_id and isinstance(sender_id, str):
        conversation_store.assign_conversation(conversation_id, sender_id)

    cancelled = conversation_store.cancel_pending_ai_messages(conversation_id, reason="Agent replied manually")
    for cid in cancelled:
        _scheduled_message_ids.discard(cid)

    messenger = get_twilio_messenger()
    if not messenger:
        abort(503, description="Twilio not configured for outbound messaging.")

    try:
        sid = messenger.send_whatsapp_message(to=f"whatsapp:{conversation_id}", body=text)
    except TwilioRestException as exc:
        logging.error(f"❌ Twilio error {exc.code} ({exc.status}): {exc.msg}")
        status, error_message = "failed", f"Twilio error {exc.code}: {exc.msg}"
    except Exception as exc:
        logging.exception("Unexpected error sending manual message via Twilio")
        status, error_message = "failed", str(exc)

    message = conversation_store.record_message(
        conversation_id, text=text, author="agent", direction="outbound",
        via=delivery_via, transport_sid=sid, sent_at=_iso_now() if status == "sent" else None,
        status=status, error=error_message,
    )

    payload = {"status": status, "sid": sid, "message": message.to_dict()}
    if error_message:
        payload["error"] = error_message
    return jsonify(payload), (200 if status == "sent" else 202)


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
    draft = _build_reply(latest.text, latest.attachments)
    return jsonify({"draft": draft, "model": "gpt-4o-mini"})


# -----------------------------------------------------------
# Run server
# -----------------------------------------------------------
if __name__ == "__main__":
    print("\n🔧 Twilio environment snapshot:")
    print(f"  Account SID: {os.getenv('TWILIO_ACCOUNT_SID')}")
    print(f"  Messaging Service SID: {os.getenv('TWILIO_MESSAGING_SERVICE_SID')}")
    print(f"  WhatsApp From: {os.getenv('TWILIO_WHATSAPP_NUMBER')}")
    app.run(host="0.0.0.0", port=5002, debug=True)
