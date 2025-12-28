"""Persist and load per-account integration credentials.

This module keeps Twilio and OpenAI credentials in a Firestore document under
`accounts/{accountId}/settings/integrations`. Secrets are only surfaced to the
API layer as "configured" booleans; the raw values are used server-side for
Twilio/OpenAI clients.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import firebase_admin
from firebase_admin import credentials, exceptions as firebase_exceptions, firestore
from google.auth import exceptions as google_auth_exceptions

logger = logging.getLogger(__name__)

_FIREBASE_APP = None


def _get_firebase_app():
    global _FIREBASE_APP
    if _FIREBASE_APP is not None:
        return _FIREBASE_APP
    try:
        _FIREBASE_APP = firebase_admin.get_app()
    except ValueError:
        cred_path = os.getenv("FIREBASE_CREDENTIALS_FILE")
        credentials_obj = credentials.Certificate(cred_path) if cred_path else None
        try:
            _FIREBASE_APP = firebase_admin.initialize_app(credentials_obj)
        except google_auth_exceptions.DefaultCredentialsError as exc:  # type: ignore[attr-defined]
            logger.error(
                "🔥 Firebase credentials are missing or invalid. "
                "Set FIREBASE_CREDENTIALS_FILE or GOOGLE_APPLICATION_CREDENTIALS to a valid service account JSON. "
                "Original error: %s",
                exc,
            )
            raise
        except firebase_exceptions.FirebaseError as exc:
            logger.error(
                "🔥 Firebase failed to initialize with the provided credentials file (%s): %s",
                cred_path or "not provided",
                exc,
            )
            raise
        except Exception as exc:  # pragma: no cover - safeguard for unexpected errors
            logger.error("🔥 Unexpected error initializing Firebase: %s", exc)
            raise
    return _FIREBASE_APP


def _firestore_client():
    try:
        return firestore.client(app=_get_firebase_app())
    except google_auth_exceptions.DefaultCredentialsError as exc:  # type: ignore[attr-defined]
        logger.error(
            "🚫 Firestore client creation failed: Google Application Default Credentials were not found. "
            "Set FIREBASE_CREDENTIALS_FILE or GOOGLE_APPLICATION_CREDENTIALS to your service account JSON. "
            "Original error: %s",
            exc,
        )
        raise
    except Exception as exc:
        logger.error("🚫 Firestore client creation failed: %s", exc)
        raise


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


@dataclass
class TwilioSettings:
    account_sid: Optional[str] = None
    auth_token: Optional[str] = None
    messaging_service_sid: Optional[str] = None
    whatsapp_from: Optional[str] = None
    sandbox_mode: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.account_sid and self.auth_token)


@dataclass
class OpenAISettings:
    api_key: Optional[str] = None
    organization_id: Optional[str] = None
    base_url: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@dataclass
class IntegrationSettings:
    twilio: Optional[TwilioSettings] = None
    openai: Optional[OpenAISettings] = None
    other_notes: Optional[str] = None

    @property
    def ready(self) -> bool:
        twilio_ready = bool(self.twilio and self.twilio.configured)
        ai_ready = bool(self.openai and self.openai.configured)
        return twilio_ready and ai_ready

    def to_firestore(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if self.twilio:
            twilio_payload = {
                "accountSid": self.twilio.account_sid,
                "authToken": self.twilio.auth_token,
                "messagingServiceSid": self.twilio.messaging_service_sid,
                "whatsappFrom": self.twilio.whatsapp_from,
                "sandboxMode": self.twilio.sandbox_mode,
            }
            payload["twilio"] = {k: v for k, v in twilio_payload.items() if v not in (None, "")}
        if self.openai:
            openai_payload = {
                "apiKey": self.openai.api_key,
                "organizationId": self.openai.organization_id,
                "baseUrl": self.openai.base_url,
            }
            payload["openAi"] = {k: v for k, v in openai_payload.items() if v not in (None, "")}
        if self.other_notes:
            payload["otherNotes"] = self.other_notes
        return payload

    def to_safe_dict(self) -> Dict[str, Any]:
        return {
            "ready": self.ready,
            "twilio": {
                "accountSid": self.twilio.account_sid if self.twilio else None,
                "messagingServiceSid": self.twilio.messaging_service_sid if self.twilio else None,
                "whatsappFrom": self.twilio.whatsapp_from if self.twilio else None,
                "sandboxMode": self.twilio.sandbox_mode if self.twilio else False,
                "authTokenConfigured": bool(self.twilio and self.twilio.auth_token),
            },
            "openAi": {
                "organizationId": self.openai.organization_id if self.openai else None,
                "baseUrl": self.openai.base_url if self.openai else None,
                "apiKeyConfigured": bool(self.openai and self.openai.api_key),
            },
            "otherNotes": self.other_notes,
        }


class IntegrationSettingsStore:
    def __init__(self, *, client=None) -> None:
        self._client = client or _firestore_client()

    def _doc_ref(self, account_id: str):
        if not account_id:
            raise ValueError("account_id is required for integration settings")
        return (
            self._client.collection("accounts")
            .document(account_id)
            .collection("settings")
            .document("integrations")
        )

    def load(self, account_id: str) -> IntegrationSettings:
        doc = self._doc_ref(account_id).get()
        if not doc.exists:
            return IntegrationSettings()

        data = doc.to_dict() or {}
        twilio_data = data.get("twilio") or {}
        openai_data = data.get("openAi") or {}

        twilio = None
        if any(twilio_data.values()):
            twilio = TwilioSettings(
                account_sid=_clean(twilio_data.get("accountSid")),
                auth_token=_clean(twilio_data.get("authToken")),
                messaging_service_sid=_clean(twilio_data.get("messagingServiceSid")),
                whatsapp_from=_clean(twilio_data.get("whatsappFrom")),
                sandbox_mode=bool(twilio_data.get("sandboxMode", False)),
            )

        openai = None
        if any(openai_data.values()):
            openai = OpenAISettings(
                api_key=_clean(openai_data.get("apiKey")),
                organization_id=_clean(openai_data.get("organizationId")),
                base_url=_clean(openai_data.get("baseUrl")),
            )

        other_notes = _clean(data.get("otherNotes"))

        return IntegrationSettings(twilio=twilio, openai=openai, other_notes=other_notes)

    def update(
        self,
        account_id: str,
        *,
        twilio_updates: Optional[Dict[str, Any]] = None,
        openai_updates: Optional[Dict[str, Any]] = None,
        other_notes: Optional[str] = None,
    ) -> IntegrationSettings:
        current = self.load(account_id)

        if twilio_updates is not None:
            twilio = current.twilio or TwilioSettings()
            account_sid = _clean(twilio_updates.get("accountSid", twilio.account_sid))
            auth_token = _clean(twilio_updates.get("authToken", twilio.auth_token))
            messaging_service_sid = _clean(
                twilio_updates.get("messagingServiceSid", twilio.messaging_service_sid)
            )
            whatsapp_from = _clean(twilio_updates.get("whatsappFrom", twilio.whatsapp_from))
            sandbox_mode = bool(twilio_updates.get("sandboxMode", twilio.sandbox_mode))
            current.twilio = TwilioSettings(
                account_sid=account_sid,
                auth_token=auth_token,
                messaging_service_sid=messaging_service_sid,
                whatsapp_from=whatsapp_from,
                sandbox_mode=sandbox_mode,
            )

        if openai_updates is not None:
            openai = current.openai or OpenAISettings()
            api_key = _clean(openai_updates.get("apiKey", openai.api_key))
            organization_id = _clean(openai_updates.get("organizationId", openai.organization_id))
            base_url = _clean(openai_updates.get("baseUrl", openai.base_url))
            current.openai = OpenAISettings(
                api_key=api_key,
                organization_id=organization_id,
                base_url=base_url,
            )

        if other_notes is not None:
            current.other_notes = _clean(other_notes)

        # Replace the document to avoid leaving stale fields around.
        self._doc_ref(account_id).set(current.to_firestore())
        return current


integration_settings_store = IntegrationSettingsStore()
