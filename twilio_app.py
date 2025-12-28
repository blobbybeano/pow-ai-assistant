"""Twilio webhook + REST API backing the PowWash WhatsApp workspace (production-safe)."""

from __future__ import annotations

import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Dict, List, Set
from uuid import uuid4

import firebase_admin
import requests
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials, firestore
from flask import Flask, Response, abort, g, jsonify, request, send_from_directory
from flask_cors import CORS
from openai import OpenAI
from twilio.base.exceptions import TwilioRestException
from twilio.twiml.messaging_response import MessagingResponse
from flask_cors import cross_origin

from auto_responder import generate_reply
from conversation_store import conversation_store
from twilio_helpers import TwilioConfig, TwilioMessenger
from integration_settings import IntegrationSettingsStore, integration_settings_store

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
_integration_store: IntegrationSettingsStore = integration_settings_store


# -----------------------------------------------------------
# Firebase Auth / Firestore helpers
# -----------------------------------------------------------
_FIREBASE_APP = None


def _load_account_settings(account_id: str | None):
    if not account_id:
        return None
    try:
        return _integration_store.load(account_id)
    except Exception:
        logging.exception("Failed to load integration settings for account %s", account_id)
        return None


def _get_firebase_app():
    global _FIREBASE_APP
    if _FIREBASE_APP is not None:
        return _FIREBASE_APP
    try:
        _FIREBASE_APP = firebase_admin.get_app()
    except ValueError:
        cred_path = os.getenv("FIREBASE_CREDENTIALS_FILE")
        credentials_obj = credentials.Certificate(cred_path) if cred_path else None
        _FIREBASE_APP = firebase_admin.initialize_app(credentials_obj)
    return _FIREBASE_APP


def _firestore_client():
    return firestore.client(app=_get_firebase_app())


def _verify_account_membership():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        abort(401, description="Missing bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    try:
        decoded = firebase_auth.verify_id_token(token, app=_get_firebase_app())
    except Exception:
        abort(401, description="Invalid or expired token")

    uid = decoded.get("uid")
    db = _firestore_client()
    membership_query = (
        db.collection_group("members").where("userId", "==", uid).limit(1)
    )
    membership_docs = list(membership_query.stream())
    if not membership_docs:
        abort(403, description="User is not a member of any account")
    membership = membership_docs[0]
    account_ref = membership.reference.parent.parent
    role = membership.to_dict().get("role", "staff")
    g.account_id = account_ref.id if account_ref else None
    g.member_role = role
    g.user_id = uid


def require_account_member(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        _verify_account_membership()
        return handler(*args, **kwargs)

    return wrapper


def require_admin(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        _verify_account_membership()
        if getattr(g, "member_role", "staff") != "admin":
            abort(403, description="Admin privileges required")
        return handler(*args, **kwargs)

    return wrapper


# -----------------------------------------------------------
# Twilio Messenger dynamic builder
# -----------------------------------------------------------
def get_twilio_messenger(account_id: str | None = None) -> TwilioMessenger | None:
    """Build a TwilioMessenger from stored per-account settings with env fallback."""
    acct = account_id
    settings = _load_account_settings(acct)
    twilio_settings = settings.twilio if settings else None

    if twilio_settings:
        messenger = TwilioMessenger.from_settings(
            TwilioConfig(
                account_sid=twilio_settings.account_sid or "",
                auth_token=twilio_settings.auth_token or "",
                messaging_service_sid=twilio_settings.messaging_service_sid,
                whatsapp_from=twilio_settings.whatsapp_from,
            )
        )
        if messenger:
            return messenger
        logging.warning("⚠️ Stored Twilio settings are present but incomplete.")
        return None

    messenger = TwilioMessenger.from_env()
    if messenger:
        cfg = messenger._config
        if cfg.messaging_service_sid:
            cfg.whatsapp_from = None
        return messenger

    logging.warning("⚠️ Twilio credentials not detected or invalid.")
    return None


# -----------------------------------------------------------
# OpenAI client builder
# -----------------------------------------------------------
def _build_openai_client(account_id: str | None = None) -> OpenAI:
    """Instantiate an OpenAI client, preferring stored per-account credentials."""
    acct = account_id
    overrides = {}
    settings = _load_account_settings(acct)
    openai_settings = settings.openai if settings else None
    if openai_settings:
        if openai_settings.api_key:
            overrides["api_key"] = openai_settings.api_key
        if openai_settings.organization_id:
            overrides["organization"] = openai_settings.organization_id
        if openai_settings.base_url:
            overrides["base_url"] = openai_settings.base_url

    if overrides:
        try:
            return OpenAI(**overrides)
        except Exception:
            logging.exception("Failed to instantiate OpenAI client with stored settings")
            raise

    return OpenAI()


# -----------------------------------------------------------
# Integration test helpers
# -----------------------------------------------------------
def _test_twilio_connection(account_id: str | None):
    settings = _load_account_settings(account_id)

    messenger = None
    twilio_settings = settings.twilio if settings else None
    if twilio_settings:
        messenger = TwilioMessenger.from_settings(
            TwilioConfig(
                account_sid=twilio_settings.account_sid or "",
                auth_token=twilio_settings.auth_token or "",
                messaging_service_sid=twilio_settings.messaging_service_sid,
                whatsapp_from=twilio_settings.whatsapp_from,
            )
        )
    else:
        messenger = TwilioMessenger.from_env()

    if messenger is None:
        return False, "Twilio credentials are not configured for this workspace.", None

    config = messenger._config
    try:
        if config.messaging_service_sid:
            service = messenger._client.messaging.services(config.messaging_service_sid).fetch()
            return True, f"Messaging Service {service.sid} is reachable.", service.sid

        account = messenger._client.api.accounts(config.account_sid).fetch()
        return True, f"Twilio account {account.sid} is reachable.", account.sid
    except TwilioRestException as exc:
        logging.error("Twilio validation failed: %s", exc, exc_info=True)
        identifier = config.messaging_service_sid or config.account_sid
        message = f"Twilio error {exc.code}: {exc.msg}"
        return False, message, identifier
    except Exception as exc:
        logging.exception("Unexpected error validating Twilio connection")
        identifier = config.messaging_service_sid or config.account_sid
        return False, str(exc), identifier


def _test_openai_connection(account_id: str | None):
    try:
        client = _build_openai_client(account_id)
    except Exception as exc:
        logging.exception("OpenAI client initialization failed")
        return False, str(exc), None
    try:
        models = client.models.list()
        first_id = None
        try:
            first_id = models.data[0].id if getattr(models, "data", None) else None
        except Exception:
            first_id = None
        message = "OpenAI credentials validated."
        if first_id:
            message = f"OpenAI credentials validated; first model: {first_id}."
        return True, message, first_id
    except Exception as exc:
        logging.exception("OpenAI validation failed")
        return False, str(exc), None


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


def _collect_inbound_attachments(form) -> List[dict]:
    """Download and persist inbound WhatsApp media attachments."""
    attachments: List[dict] = []
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
        attachment_payload = {"path": str(file_path)}
        if content_type:
            attachment_payload["content_type"] = content_type
        attachments.append(attachment_payload)
        logging.info("📁 Stored local media path for AI processing: %s", file_path)

    return attachments


def _build_reply(
    inbound_text: str,
    attachments: List[str] | None = None,
    *,
    account_id: str | None = None,
) -> str:
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

    client = _build_openai_client(account_id)

    return generate_reply(
        message=sanitized_text,
        price_list_path=PRICE_LIST_PATH,
        tone_profile_path=TONE_PROFILE_PATH,
        model="gpt-4o-mini",
        temperature=0.5,
        attachments=attachment_list,
        client=client,
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


def _resolve_account_id_from_twilio_payload(
    *,
    messaging_service_sid: str | None,
    to_address: str | None,
) -> str | None:
    """Determine the owning account for an incoming Twilio webhook."""
    client = _firestore_client()

    def _account_from_settings_doc(doc) -> str | None:
        parent = doc.reference.parent if doc else None
        if parent and parent.parent:
            return parent.parent.id
        return None

    def _lookup_account(field_path: str, value: str) -> str | None:
        try:
            account_query = client.collection("accounts").where(field_path, "==", value).limit(1)
            for doc in account_query.stream():
                return doc.id
        except Exception:
            logging.exception("Failed to query accounts by %s", field_path)
            raise

        try:
            settings_query = (
                client.collection_group("settings")
                .where(field_path, "==", value)
                .limit(1)
            )
            for doc in settings_query.stream():
                account_id = _account_from_settings_doc(doc)
                if account_id:
                    return account_id
        except Exception:
            logging.exception("Failed to query account settings by %s", field_path)
            raise

        return None

    if messaging_service_sid:
        account_id = _lookup_account("twilio.messagingServiceSid", messaging_service_sid)
        if account_id:
            return account_id

    normalized_to = _normalize_msisdn(to_address or "")
    to_candidates: List[str] = []
    for candidate in (to_address, normalized_to):
        if candidate and candidate not in to_candidates:
            to_candidates.append(candidate)
    if normalized_to:
        whatsapp_prefixed = f"whatsapp:{normalized_to}"
        if whatsapp_prefixed not in to_candidates:
            to_candidates.append(whatsapp_prefixed)

    for candidate in to_candidates:
        account_id = _lookup_account("twilio.whatsappFrom", candidate)
        if account_id:
            return account_id

    return None


def _iso_now() -> datetime:
    return datetime.now(timezone.utc)


# -----------------------------------------------------------
# AI message scheduling logic
# -----------------------------------------------------------
def _schedule_ai_delivery(
    account_id: str,
    conversation_id: str,
    message_id: str,
    body: str,
    *,
    scheduled_for: datetime,
) -> None:
    """Schedules a delayed AI message to be sent to a WhatsApp user."""
    if message_id in _scheduled_message_ids:
        return

    delay = max(0.0, (scheduled_for - datetime.now(timezone.utc)).total_seconds())

    def _deliver() -> None:
        message_snapshot = conversation_store.get_message(account_id, conversation_id, message_id)
        if not message_snapshot or message_snapshot.status != "scheduled":
            _scheduled_message_ids.discard(message_id)
            return

        messenger = get_twilio_messenger(account_id)
        if not messenger:
            logging.error("🚫 Twilio credentials missing; cannot deliver AI reply.")
            conversation_store.update_message(
                account_id,
                conversation_id,
                message_id,
                status="failed",
                sent_at=_iso_now(),
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
                account_id,
                conversation_id,
                message_id,
                status="failed",
                sent_at=_iso_now(),
                error=f"Twilio error {exc.code}: {exc.msg}",
            )
        except Exception as exc:
            logging.exception("❌ Unexpected error sending AI reply via Twilio")
            conversation_store.update_message(
                account_id,
                conversation_id,
                message_id,
                status="failed",
                sent_at=_iso_now(),
                error=str(exc),
            )
        else:
            conversation_store.update_message(
                account_id,
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
    """Re-arm any AI messages that were scheduled before server restart."""
    for account_id, conversation_id, message in conversation_store.pending_scheduled_messages():
        try:
            scheduled_for = (
                message.scheduled_send_at
                if message.scheduled_send_at
                else datetime.now(timezone.utc) + timedelta(seconds=AI_AUTOREPLY_DELAY_SECONDS)
            )
        except ValueError:
            scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=AI_AUTOREPLY_DELAY_SECONDS)

        conversation_store.update_message(
            account_id,
            conversation_id,
            message.id,
            status="scheduled",
            scheduled_send_at=scheduled_for,
        )
        _schedule_ai_delivery(account_id, conversation_id, message.id, message.text, scheduled_for=scheduled_for)


_bootstrap_pending_messages()


# -----------------------------------------------------------
# Twilio WhatsApp webhook
# -----------------------------------------------------------
@app.post("/twilio/whatsapp")
def whatsapp_webhook() -> Response:
    """Receives inbound WhatsApp messages from Twilio."""
    inbound_text = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")
    to_number = (request.form.get("To") or "").strip()
    profile_name = request.form.get("ProfileName") or request.form.get("WaId")
    profile_photo_url = request.form.get("ProfilePictureUrl") or request.form.get("ProfileImageUrl")
    wa_id = request.form.get("WaId")
    messaging_service_sid = (request.form.get("MessagingServiceSid") or "").strip()
    conversation_id = _conversation_id(from_number, wa_id)
    attachments = _collect_inbound_attachments(request.form)

    try:
        account_id = _resolve_account_id_from_twilio_payload(
            messaging_service_sid=messaging_service_sid,
            to_address=to_number,
        )
    except Exception:
        logging.exception("Failed to resolve account for incoming Twilio webhook")
        return Response(
            "Failed to resolve account for incoming Twilio webhook.",
            mimetype="text/plain",
            status=500,
        )

    if not account_id:
        logging.error(
            "🚫 No account mapping found for Twilio webhook (MessagingServiceSid=%s, To=%s)",
            messaging_service_sid or "<missing>",
            to_number or "<missing>",
        )
        return Response(
            "No matching account found for incoming Twilio webhook.",
            mimetype="text/plain",
            status=400,
        )

    conversation_store.record_message(
        account_id,
        conversation_id,
        text=inbound_text,
        author="customer",
        direction="inbound",
        profile_name=profile_name, profile_photo_url=profile_photo_url, increment_unread=True,
        attachments=attachments,
    )

    default_responder = conversation_store.get_default_responder(account_id)
    if default_responder:
        conversation_store.assign_conversation(account_id, conversation_id, default_responder)

    convo_snapshot = conversation_store.get_conversation(account_id, conversation_id)
    ai_enabled = convo_snapshot["aiEnabled"] if convo_snapshot else True
    response = MessagingResponse()

    if ai_enabled:
        drafting_message = conversation_store.record_message(
            account_id,
            conversation_id,
            text="",
            author="ai",
            direction="outbound",
            status="drafting",
        )
        try:
            reply_text = _build_reply(inbound_text, attachments, account_id=account_id)
        except Exception as exc:
            logging.exception("AI reply generation failed")
            conversation_store.update_message(
                account_id,
                conversation_id,
                drafting_message.id,
                status="failed",
                error=str(exc),
            )
            return Response(str(response), mimetype="application/xml")

        send_after = datetime.now(timezone.utc) + timedelta(seconds=AI_AUTOREPLY_DELAY_SECONDS)
        conversation_store.update_message(
            account_id,
            conversation_id,
            drafting_message.id,
            text=reply_text,
            status="scheduled",
            scheduled_send_at=send_after,
        )
        _schedule_ai_delivery(account_id, conversation_id, drafting_message.id, reply_text, scheduled_for=send_after)
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
@cross_origin()   # <-- THIS fixes your Flutter Web image loading
def serve_uploaded_file(filename: str) -> Response:
    """Expose saved media files for downstream consumption (e.g. OpenAI)."""
    return send_from_directory(UPLOADS_DIR, filename)


@app.get("/api/settings/responder")
@require_account_member
def api_get_default_responder() -> Response:
    account_id = getattr(g, "account_id", None)
    return jsonify({"defaultResponderId": conversation_store.get_default_responder(account_id)})


@app.get("/api/settings/integrations")
@require_account_member
def api_get_integrations() -> Response:
    account_id = getattr(g, "account_id", None)
    if not account_id:
        abort(400, description="Account not resolved")
    settings = _integration_store.load(account_id)
    return jsonify(settings.to_safe_dict())


@app.post("/api/settings/integrations")
@require_admin
def api_update_integrations() -> Response:
    account_id = getattr(g, "account_id", None)
    if not account_id:
        abort(400, description="Account not resolved")

    payload = request.get_json(silent=True) or {}
    twilio_updates = payload.get("twilio") if isinstance(payload.get("twilio"), dict) else None
    openai_updates = payload.get("openAi") if isinstance(payload.get("openAi"), dict) else None
    other_notes = payload.get("otherNotes")

    settings = _integration_store.update(
        account_id,
        twilio_updates=twilio_updates,
        openai_updates=openai_updates,
        other_notes=other_notes if isinstance(other_notes, str) else None,
    )

    return jsonify(settings.to_safe_dict())


@app.post("/api/settings/test-twilio")
@require_account_member
def api_test_twilio_settings() -> Response:
    account_id = getattr(g, "account_id", None)
    ok, message, identifier = _test_twilio_connection(account_id)
    payload = {"ok": ok, "message": message}
    if identifier:
        payload["serviceSid"] = identifier
    status = 200 if ok else 502
    return jsonify(payload), status


@app.post("/api/settings/test-openai")
@require_account_member
def api_test_openai_settings() -> Response:
    account_id = getattr(g, "account_id", None)
    ok, message, model_id = _test_openai_connection(account_id)
    payload = {"ok": ok, "message": message}
    if model_id:
        payload["modelId"] = model_id
    status = 200 if ok else 502
    return jsonify(payload), status


@app.post("/api/settings/responder")
@require_admin
def api_set_default_responder() -> Response:
    payload = request.get_json(silent=True) or {}
    responder_id = payload.get("responderId")
    if responder_id is not None and not isinstance(responder_id, str):
        abort(400, description="responderId must be a string")
    conversation_store.set_default_responder(responder_id, account_id=g.account_id)
    return jsonify({"defaultResponderId": conversation_store.get_default_responder(g.account_id)})


@app.get("/api/conversations")
@require_account_member
def api_list_conversations() -> Response:
    conversations = conversation_store.list_conversations(g.account_id)
    return jsonify({"conversations": conversations})


@app.get("/api/conversations/<conversation_id>")
@require_account_member
def api_get_conversation(conversation_id: str) -> Response:
    convo = conversation_store.get_conversation(g.account_id, conversation_id, mark_read=True)
    if convo is None:
        abort(404, description="Conversation not found")
    return jsonify(convo)


@app.post("/api/conversations/<conversation_id>/toggle-ai")
@require_account_member
def api_toggle_ai(conversation_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    enabled = bool(payload.get("enabled", True))
    responder_id = payload.get("responderId")
    if responder_id:
        conversation_store.assign_conversation(g.account_id, conversation_id, responder_id)
    result = conversation_store.set_ai_enabled(g.account_id, conversation_id, enabled)
    return jsonify({"enabled": result})


@app.post("/api/conversations/<conversation_id>/messages")
@require_account_member
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
        conversation_store.assign_conversation(g.account_id, conversation_id, sender_id)

    cancelled = conversation_store.cancel_pending_ai_messages(
        g.account_id, conversation_id, reason="Agent replied manually"
    )
    for cid in cancelled:
        _scheduled_message_ids.discard(cid)

    messenger = get_twilio_messenger(g.account_id)
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
        g.account_id,
        conversation_id,
        text=text,
        author="agent",
        direction="outbound",
        via=delivery_via,
        transport_sid=sid,
        sent_at=_iso_now() if status == "sent" else None,
        status=status,
        error=error_message,
    )

    payload = {"status": status, "sid": sid, "message": message.to_dict()}
    if error_message:
        payload["error"] = error_message
    return jsonify(payload), (200 if status == "sent" else 202)


@app.post("/api/conversations/<conversation_id>/messages/<message_id>/cancel")
@require_account_member
def api_cancel_ai_message(conversation_id: str, message_id: str) -> Response:
    message = conversation_store.cancel_scheduled_message(g.account_id, conversation_id, message_id)
    if message is None:
        abort(404, description="Scheduled AI message not found")
    _scheduled_message_ids.discard(message_id)
    return jsonify({"status": "cancelled", "message": message.to_dict()})


@app.post("/api/conversations/<conversation_id>/ai-draft")
@require_account_member
def api_generate_ai_draft(conversation_id: str) -> Response:
    convo = conversation_store.get_conversation(g.account_id, conversation_id)
    if convo is None:
        abort(404, description="Conversation not found")
    latest = conversation_store.latest_customer_message(g.account_id, conversation_id)
    if latest is None:
        abort(400, description="No customer message available for drafting")
    draft = _build_reply(latest.text, latest.attachments, account_id=g.account_id)
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
