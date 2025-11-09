"""Twilio webhook + REST API backing the PowWash WhatsApp workspace (production-safe)."""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin
from uuid import uuid4

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename
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

AI_AUTOREPLY_DELAY_SECONDS = 180
_scheduled_message_ids: Set[str] = set()

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_BASE_URL = os.getenv("MEDIA_BASE_URL")
twilio_messenger: Optional[TwilioMessenger] = None


# -----------------------------------------------------------
# Twilio Messenger dynamic builder
# -----------------------------------------------------------
def get_twilio_messenger() -> TwilioMessenger | None:
    """
    Always rebuild the TwilioMessenger from fresh environment variables.
    This prevents stale 'from_' values and ensures Messaging Service SID takes priority.
    """
    global twilio_messenger
    if twilio_messenger is not None:
        return twilio_messenger

    messenger = TwilioMessenger.from_env()
    if messenger:
        twilio_messenger = messenger
        return twilio_messenger

    logging.warning("⚠️ Twilio credentials not detected or invalid.")
    return None


# -----------------------------------------------------------
# Utility functions
# -----------------------------------------------------------
_EMPTY_INBOUND_REPLY = (
    "Hi there! This is PowWash. I didn’t catch your message—"
    "could you please resend it so we can prepare your quote?"
)


def _attachment_caption(payload: Dict[str, Any]) -> Optional[str]:
    url = (payload.get("url") or "").strip()
    content_type = (payload.get("contentType") or "").lower()
    filename = (payload.get("filename") or "").strip()

    if not url and not filename:
        return None

    label = "image" if content_type.startswith("image/") else "attachment"
    if filename:
        label = f"{label} '{filename}'"

    if url:
        return f"[{label} shared: {url}]"
    return f"[{label} shared]"


def _conversation_history(conversation_id: str, *, limit: int = 20) -> List[Dict[str, str]]:
    convo = conversation_store.get_conversation(conversation_id)
    if convo is None:
        return []

    history: List[Dict[str, str]] = []
    messages: List[Dict[str, Any]] = convo.get("messages", [])
    for message in messages[-limit:]:
        author = message.get("author", "customer")
        text = (message.get("text") or "").strip()
        attachments = message.get("attachments") or []

        fragments: List[str] = []
        if text:
            fragments.append(text)
        for attachment in attachments:
            caption = _attachment_caption(attachment)
            if caption:
                fragments.append(caption)

        if not fragments:
            continue

        speaker: str
        role: str
        if author == "customer":
            speaker, role = "Customer", "user"
        elif author == "agent":
            speaker, role = "Human agent", "assistant"
        elif author == "ai":
            speaker, role = "AI assistant", "assistant"
        else:
            speaker, role = "System", "assistant"

        history.append({"role": role, "content": f"{speaker}: {' '.join(fragments)}"})

    return history[-limit:]


def _build_reply(conversation_id: str) -> str:
    """Generate an AI PowWash reply using the full conversation history."""
    history = _conversation_history(conversation_id)
    if not history or history[-1]["role"] != "user":
        return _EMPTY_INBOUND_REPLY

    trimmed_history = history[-12:]
    return generate_reply(
        conversation_history=trimmed_history,
        price_list_path=PRICE_LIST_PATH,
        tone_profile_path=TONE_PROFILE_PATH,
        model="gpt-4o-mini",
        temperature=0.5,
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


def _collect_inbound_attachments(form_data) -> List[Dict[str, str]]:
    attachments: List[Dict[str, str]] = []
    try:
        count = int(form_data.get("NumMedia", "0") or 0)
    except (TypeError, ValueError):
        count = 0

    for index in range(count):
        url = (form_data.get(f"MediaUrl{index}") or "").strip()
        content_type = (form_data.get(f"MediaContentType{index}") or "").strip()
        filename = (
            form_data.get(f"MediaFilename{index}")
            or form_data.get(f"MediaFileName{index}")
            or ""
        ).strip()

        if not url:
            continue

        attachments.append(
            {
                "url": url,
                "contentType": content_type or None,
                "filename": filename or None,
            }
        )

    return attachments


def _parse_outbound_attachments(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    attachments: List[Dict[str, str]] = []
    raw = payload.get("attachments")
    if not isinstance(raw, list):
        return attachments

    for item in raw:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        content_type = (item.get("contentType") or "").strip() or None
        filename = (item.get("filename") or "").strip() or None
        attachments.append({"url": url, "contentType": content_type, "filename": filename})

    return attachments


def _public_upload_url(filename: str) -> str:
    if MEDIA_BASE_URL:
        base = MEDIA_BASE_URL.rstrip("/") + "/"
        return urljoin(base, f"uploads/{filename}")
    return url_for("serve_upload", filename=filename, _external=True)


def _persist_uploaded_file(file_storage) -> Dict[str, str]:
    content_type = (file_storage.mimetype or "").lower()
    if not content_type.startswith("image/"):
        abort(400, description="Only image uploads are supported")

    original_name = secure_filename(file_storage.filename or "customer-photo")
    extension = Path(original_name).suffix
    if not extension:
        guessed = mimetypes.guess_extension(content_type) or ""
        extension = guessed

    filename = f"{uuid4().hex}{extension}" if extension else uuid4().hex
    storage_path = UPLOADS_DIR / filename
    file_storage.save(storage_path)

    return {
        "id": filename,
        "url": _public_upload_url(filename),
        "contentType": content_type,
        "filename": original_name,
    }


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
            reply_text = _build_reply(conversation_id)
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


@app.post("/api/uploads")
def api_upload_attachment() -> Response:
    if "file" not in request.files:
        abort(400, description="No file part in upload request")

    file_storage = request.files["file"]
    if not file_storage or not file_storage.filename:
        abort(400, description="Uploaded file is missing a filename")

    metadata = _persist_uploaded_file(file_storage)
    return jsonify(metadata), 201


@app.get("/uploads/<path:filename>")
def serve_upload(filename: str):
    return send_from_directory(UPLOADS_DIR, filename)


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
    attachments = _parse_outbound_attachments(payload)

    if not text and not attachments:
        abort(400, description="Message text or image attachment is required")

    status, sid, error_message = "sent", None, None
    delivery_via = "whatsapp"

    if sender_id and isinstance(sender_id, str):
        conversation_store.assign_conversation(conversation_id, sender_id)

    cancelled = conversation_store.cancel_pending_ai_messages(
        conversation_id,
        reason="Cancelled because an agent replied manually",
    )
    for cid in cancelled:
        _scheduled_message_ids.discard(cid)

    messenger = get_twilio_messenger()
    if messenger:
        try:
            sid = messenger.send_whatsapp_message(
                to=f"whatsapp:{conversation_id}",
                body=text,
                media_urls=[attachment["url"] for attachment in attachments] if attachments else None,
            )
        except TwilioRestException as exc:
            logging.error(f"❌ Twilio error {exc.code} ({exc.status}): {exc.msg}")
            status, error_message = "failed", f"Twilio error {exc.code}: {exc.msg}"
        except Exception as exc:
            logging.exception("Unexpected error sending manual message via Twilio")
            status, error_message = "failed", str(exc)
    else:
        sid = f"local-{uuid4().hex}"
        delivery_via = "workspace"

    message = conversation_store.record_message(
        conversation_id, text=text, author="agent", direction="outbound",
        via=delivery_via, transport_sid=sid, sent_at=_iso_now() if status == "sent" else None,
        status=status, error=error_message, attachments=attachments,
    )

    payload = {
        "status": status,
        "sid": sid,
        "delivery": delivery_via,
        "message": message.to_dict(),
    }
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


@app.post("/api/conversations/<conversation_id>/messages/<message_id>/send-now")
def api_send_scheduled_now(conversation_id: str, message_id: str) -> Response:
    message = conversation_store.get_message(conversation_id, message_id)
    if message is None or message.author != "ai":
        abort(404, description="AI message not found")

    if message.status not in {"scheduled", "drafting"}:
        abort(400, description="Message is not waiting to be sent")

    if not message.text.strip() and not message.attachments:
        abort(400, description="AI message has no content to send")

    messenger = get_twilio_messenger()
    if not messenger:
        abort(503, description="Twilio not configured for outbound messaging.")

    media_urls = [attachment.url for attachment in message.attachments if attachment.url]

    status = "sent"
    sid: Optional[str] = None
    error_message: Optional[str] = None

    try:
        sid = messenger.send_whatsapp_message(
            to=f"whatsapp:{conversation_id}",
            body=message.text,
            media_urls=media_urls if media_urls else None,
        )
    except TwilioRestException as exc:
        logging.error(f"❌ Twilio error {exc.code} ({exc.status}): {exc.msg}")
        status, error_message = "failed", f"Twilio error {exc.code}: {exc.msg}"
    except Exception as exc:
        logging.exception("Unexpected error sending scheduled AI message immediately")
        status, error_message = "failed", str(exc)

    updated = conversation_store.update_message(
        conversation_id,
        message_id,
        status=status,
        sent_at=_iso_now(),
        transport_sid=sid,
        error=error_message,
        scheduled_send_at=None,
    )

    _scheduled_message_ids.discard(message_id)

    payload = {
        "status": status,
        "sid": sid,
        "message": (updated or message).to_dict(),
    }
    if error_message:
        payload["error"] = error_message

    return jsonify(payload), (200 if status == "sent" else 202)


@app.post("/api/conversations/<conversation_id>/ai-draft")
def api_generate_ai_draft(conversation_id: str) -> Response:
    convo = conversation_store.get_conversation(conversation_id)
    if convo is None:
        abort(404, description="Conversation not found")
    history = _conversation_history(conversation_id)
    if not history or history[-1]["role"] != "user":
        abort(400, description="No customer message available for drafting")
    draft = _build_reply(conversation_id)
    return jsonify({"draft": draft, "model": "gpt-4o-mini"})


# -----------------------------------------------------------
# Run server
# -----------------------------------------------------------
if __name__ == "__main__":
    import os
    print("\n🔧 Twilio environment snapshot:")
    print(f"  Account SID: {os.getenv('TWILIO_ACCOUNT_SID')}")
    print(f"  Messaging Service SID: {os.getenv('TWILIO_MESSAGING_SERVICE_SID')}")
    print(f"  WhatsApp From: {os.getenv('TWILIO_WHATSAPP_NUMBER')}")
    app.run(host="0.0.0.0", port=5002, debug=True)
