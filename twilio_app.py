"""Twilio webhook + REST API backing the PowWash WhatsApp workspace."""

from __future__ import annotations

import base64
import logging
import mimetypes
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple
from uuid import uuid4

from flask import Flask, Response, abort, jsonify, request, send_file, url_for
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

from auto_responder import generate_reply
from conversation_store import MessageAttachment, conversation_store
from twilio_helpers import TwilioMessenger

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

PRICE_LIST_PATH = Path("price_list.json")
TONE_PROFILE_PATH = Path("tone_profile.md")
MEDIA_CACHE_DIR = Path("media_cache")
MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_MEDIA_CACHE_ROOT = MEDIA_CACHE_DIR.resolve()

twilio_messenger = TwilioMessenger.from_env()
if not twilio_messenger:
    logging.warning(
        "Twilio credentials not detected. Outbound replies will be simulated locally."
    )

AI_AUTOREPLY_DELAY_SECONDS = 180

_scheduled_message_ids: Set[str] = set()


def _safe_path_segment(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", value)
    sanitized = sanitized.strip("_")
    return sanitized or "item"


def _resolve_cached_path(relative_path: str) -> Optional[Path]:
    if not relative_path:
        return None

    candidate = (MEDIA_CACHE_DIR / Path(relative_path)).resolve()
    if candidate == _MEDIA_CACHE_ROOT or _MEDIA_CACHE_ROOT in candidate.parents:
        return candidate
    return None


def _store_cached_media(
    conversation_id: str,
    message_id: str,
    attachment_id: str,
    media_bytes: bytes,
    content_type: str,
) -> Optional[str]:
    safe_convo = _safe_path_segment(conversation_id)
    safe_message = _safe_path_segment(message_id)
    safe_attachment = _safe_path_segment(attachment_id)

    content_type = (content_type or "application/octet-stream").split(";")[0].strip()
    extension = mimetypes.guess_extension(content_type) or ".bin"

    cache_dir = MEDIA_CACHE_DIR / safe_convo
    cache_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{safe_message}_{safe_attachment}{extension}"
    file_path = cache_dir / filename

    try:
        file_path.write_bytes(media_bytes)
    except OSError:  # pragma: no cover - filesystem error
        logging.exception("Failed to cache media for attachment %s", attachment_id)
        return None

    relative_path = f"{safe_convo}/{filename}"
    return relative_path


def _collect_attachment_bytes(
    attachments: Sequence[MessageAttachment],
    *,
    conversation_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> Dict[str, Tuple[bytes, str]]:
    """Return a mapping of attachment IDs to media bytes and content type."""

    collected: Dict[str, Tuple[bytes, str]] = {}
    missing_credentials_logged = False

    for attachment in attachments:
        if not attachment.content_type.lower().startswith("image/"):
            continue

        media_bytes: Optional[bytes] = None
        content_type = attachment.content_type.split(";")[0].strip()

        if getattr(attachment, "cached_path", None):
            cache_path = _resolve_cached_path(attachment.cached_path)
            if cache_path and cache_path.exists():
                try:
                    media_bytes = cache_path.read_bytes()
                except OSError:  # pragma: no cover - filesystem error
                    logging.warning(
                        "Failed to read cached media for attachment %s", attachment.id
                    )

        if media_bytes is None:
            if not twilio_messenger:
                missing_credentials_logged = True
                continue

            try:
                media_bytes, detected_type = twilio_messenger.fetch_media(
                    attachment.source_url
                )
            except Exception:  # pragma: no cover - network call
                logging.exception("Failed to download inbound media from Twilio")
                continue

            if not media_bytes:
                continue

            content_type = (detected_type or attachment.content_type).split(";")[0].strip()

            if conversation_id and message_id:
                cached_path = _store_cached_media(
                    conversation_id, message_id, attachment.id, media_bytes, content_type
                )
                if cached_path:
                    attachment.cached_path = cached_path
                    attachment.content_type = content_type
                    conversation_store.update_attachment_metadata(
                        conversation_id,
                        message_id,
                        attachment.id,
                        cached_path=cached_path,
                        content_type=content_type,
                    )

        if media_bytes:
            collected[attachment.id] = (media_bytes, content_type)

    if missing_credentials_logged:
        logging.warning(
            "Received media attachments but Twilio credentials are missing; cannot download images for AI analysis."
        )

    return collected


def _build_reply(
    inbound_text: str,
    attachments: Sequence[MessageAttachment] = (),
    *,
    conversation_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> str:
    """Generate a PowWash response for the inbound WhatsApp message."""

    message_text = (inbound_text or "").strip()
    attachments = list(attachments or [])

    if not message_text and not attachments:
        return (
            "Hi there! This is PowWash. I didn't catch your message—"
            "could you please resend it so we can prepare your quote?"
        )

    vision_inputs: List[Dict[str, str]] = []
    if attachments:
        collected = _collect_attachment_bytes(
            attachments,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        for attachment in attachments:
            if len(vision_inputs) >= 4:
                break
            payload = collected.get(attachment.id)
            if not payload:
                continue
            media_bytes, content_type = payload
            if not media_bytes:
                continue

            encoded = base64.b64encode(media_bytes).decode("ascii")
            data_url = f"data:{content_type};base64,{encoded}"
            vision_inputs.append(
                {
                    "data_url": data_url,
                    "content_type": content_type,
                    "detail": "low",
                }
            )

    if not message_text:
        message_text = "The customer sent the following image attachments without additional text."

    if attachments:
        if vision_inputs:
            count = len(vision_inputs)
            plural = "s" if count != 1 else ""
            message_text += (
                f"\n\nThe customer included {count} image{plural}. "
                "Please reference the visuals in your response."
            )
        else:
            message_text += (
                "\n\nThe customer attempted to share media, but the images could not "
                "be retrieved. Ask them to resend if the visuals are important."
            )

    return generate_reply(
        message=message_text,
        price_list_path=PRICE_LIST_PATH,
        tone_profile_path=TONE_PROFILE_PATH,
        model="gpt-4o-mini",
        temperature=0.5,
        attachments=vision_inputs,
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
            logging.info(
                "Twilio credentials missing; marking AI reply for %s as sent locally",
                conversation_id,
            )
            conversation_store.update_message(
                conversation_id,
                message_id,
                status="sent",
                sent_at=_iso_now(),
                transport_sid=f"local-{uuid4()}",
                error=None,
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


def _attach_proxy_urls(conversation_id: str, message: Dict[str, object]) -> None:
    attachments = message.get("attachments")
    message_id = message.get("id")
    if not isinstance(attachments, list) or not isinstance(message_id, str):
        return

    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        attachment_id = attachment.get("id")
        if not isinstance(attachment_id, str):
            continue
        attachment["proxyUrl"] = url_for(
            "api_get_message_attachment",
            conversation_id=conversation_id,
            message_id=message_id,
            attachment_id=attachment_id,
        )


@app.post("/twilio/whatsapp")
def whatsapp_webhook() -> Response:
    """Return a TwiML response and update the conversation store."""

    inbound_text = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")
    profile_name = request.form.get("ProfileName") or request.form.get("WaId")
    profile_photo_url = request.form.get("ProfilePictureUrl") or request.form.get(
        "ProfileImageUrl"
    )

    try:
        num_media = int(request.form.get("NumMedia", "0"))
    except (TypeError, ValueError):
        num_media = 0

    inbound_attachments: List[MessageAttachment] = []
    for index in range(num_media):
        media_url = request.form.get(f"MediaUrl{index}")
        if not media_url:
            continue
        content_type = request.form.get(f"MediaContentType{index}") or "application/octet-stream"
        filename = (
            request.form.get(f"MediaFilename{index}")
            or request.form.get(f"MediaFileName{index}")
            or None
        )
        inbound_attachments.append(
            MessageAttachment(
                id=str(uuid4()),
                content_type=content_type,
                source_url=media_url,
                filename=filename,
            )
        )

    wa_id = request.form.get("WaId")
    conversation_id = _conversation_id(from_number, wa_id)

    inbound_message = conversation_store.record_message(
        conversation_id,
        text=inbound_text,
        author="customer",
        direction="inbound",
        profile_name=profile_name,
        profile_photo_url=profile_photo_url,
        increment_unread=True,
        attachments=inbound_attachments,
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
            reply_text = _build_reply(
                inbound_text,
                inbound_attachments,
                conversation_id=conversation_id,
                message_id=inbound_message.id,
            )
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
    for convo in conversations:
        convo_id = convo.get("id")
        last_message = convo.get("lastMessage") if isinstance(convo, dict) else None
        if isinstance(convo_id, str) and isinstance(last_message, dict):
            _attach_proxy_urls(convo_id, last_message)
    return jsonify({"conversations": conversations})


@app.get("/api/conversations/<conversation_id>")
def api_get_conversation(conversation_id: str) -> Response:
    convo = conversation_store.get_conversation(conversation_id, mark_read=True)
    if convo is None:
        abort(404, description="Conversation not found")
    for message in convo.get("messages", []):
        if isinstance(message, dict):
            _attach_proxy_urls(conversation_id, message)
    return jsonify(convo)


@app.get(
    "/api/conversations/<conversation_id>/messages/<message_id>/attachments/<attachment_id>"
)
def api_get_message_attachment(
    conversation_id: str, message_id: str, attachment_id: str
) -> Response:
    message = conversation_store.get_message(conversation_id, message_id)
    if message is None:
        abort(404, description="Message not found")

    attachment = next(
        (item for item in message.attachments if item.id == attachment_id),
        None,
    )
    if attachment is None:
        abort(404, description="Attachment not found")

    if attachment.cached_path:
        cache_path = _resolve_cached_path(attachment.cached_path)
        if cache_path and cache_path.exists():
            mimetype = attachment.content_type.split(";")[0].strip()
            return send_file(
                cache_path,
                mimetype=mimetype,
                as_attachment=False,
                download_name=attachment.filename or cache_path.name,
                max_age=60,
            )

    if not twilio_messenger:
        abort(
            503,
            description="Twilio credentials are not configured; media download unavailable",
        )

    try:
        media_bytes, detected_type = twilio_messenger.fetch_media(attachment.source_url)
    except Exception:  # pragma: no cover - network call
        logging.exception("Failed to proxy WhatsApp media from Twilio")
        abort(502, description="Failed to retrieve attachment from Twilio")

    mimetype = (detected_type or attachment.content_type).split(";")[0].strip()
    cached_path = _store_cached_media(
        conversation_id,
        message_id,
        attachment.id,
        media_bytes,
        mimetype,
    )
    if cached_path:
        conversation_store.update_attachment_metadata(
            conversation_id,
            message_id,
            attachment.id,
            cached_path=cached_path,
            content_type=mimetype,
        )

    headers = {"Cache-Control": "private, max-age=60"}
    return Response(media_bytes, mimetype=mimetype, headers=headers)


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

    sid: str
    delivery_channel = "twilio"

    if not twilio_messenger:
        delivery_channel = "local"
        sid = f"local-{uuid4()}"
        logging.info(
            "Twilio credentials missing; storing manual reply for %s locally",
            conversation_id,
        )
    else:
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

    return jsonify(
        {
            "status": "sent",
            "sid": sid,
            "message": message.to_dict(),
            "delivery": delivery_channel,
        }
    )


@app.post("/api/conversations/<conversation_id>/messages/<message_id>/cancel")
def api_cancel_ai_message(conversation_id: str, message_id: str) -> Response:
    message = conversation_store.cancel_scheduled_message(conversation_id, message_id)
    if message is None:
        abort(404, description="Scheduled AI message not found")

    _scheduled_message_ids.discard(message_id)
    return jsonify({"status": "cancelled", "message": message.to_dict()})


@app.post("/api/conversations/<conversation_id>/messages/<message_id>/send-now")
def api_send_ai_message_now(conversation_id: str, message_id: str) -> Response:
    message = conversation_store.get_message(conversation_id, message_id)
    if message is None or message.author != "ai":
        abort(404, description="AI message not found")
    if message.status != "scheduled":
        abort(400, description="Only scheduled AI messages can be sent immediately")

    scheduled_for = datetime.now(timezone.utc)
    conversation_store.update_message(
        conversation_id,
        message_id,
        scheduled_send_at=scheduled_for.isoformat(),
        status="scheduled",
        error=None,
    )

    _scheduled_message_ids.discard(message_id)
    _schedule_ai_delivery(
        conversation_id,
        message_id,
        message.text,
        scheduled_for=scheduled_for,
    )

    return jsonify(
        {
            "status": "scheduled",
            "scheduledSendAt": scheduled_for.isoformat(),
            "messageId": message_id,
        }
    )


@app.post("/api/conversations/<conversation_id>/ai-draft")
def api_generate_ai_draft(conversation_id: str) -> Response:
    convo = conversation_store.get_conversation(conversation_id)
    if convo is None:
        abort(404, description="Conversation not found")

    latest = conversation_store.latest_customer_message(conversation_id)
    if latest is None:
        abort(400, description="No customer message available for drafting")

    draft = _build_reply(
        latest.text,
        latest.attachments,
        conversation_id=conversation_id,
        message_id=latest.id,
    )

    return jsonify({"draft": draft, "model": "gpt-4o-mini"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
