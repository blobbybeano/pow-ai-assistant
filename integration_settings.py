"""Persisted integration credentials per account.

This module centralises access to the OpenAI and Twilio credentials that power
each workspace. Values are stored under `accounts/{accountId}/settings` in
Firestore so every account can bring its own providers without sharing global
environment variables.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import firebase_admin
from firebase_admin import credentials, firestore


# ---------------------------------------------------------------------------
# Firestore helper
# ---------------------------------------------------------------------------
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
        _FIREBASE_APP = firebase_admin.initialize_app(credentials_obj)
    return _FIREBASE_APP


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def _clean_secret(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return str(value)


def _mask_secret(value: Optional[str], *, keep_start: int = 4, keep_end: int = 2) -> Optional[str]:
    if not value:
        return None
    if len(value) <= keep_start + keep_end:
        return "•" * len(value)
    return f"{value[:keep_start]}…{value[-keep_end:]}"


@dataclass
class IntegrationSettings:
    account_id: str
    openai_api_key: Optional[str] = None
    openai_org_id: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_messaging_service_sid: Optional[str] = None
    twilio_whatsapp_number: Optional[str] = None
    twilio_sandbox_mode: bool = False

    @classmethod
    def from_firestore(cls, account_id: str, payload: Optional[Dict[str, Any]]) -> "IntegrationSettings":
        data = payload or {}
        return cls(
            account_id=account_id,
            openai_api_key=_clean_secret(data.get("openaiApiKey")),
            openai_org_id=_clean_secret(data.get("openaiOrgId")),
            twilio_account_sid=_clean_secret(data.get("twilioAccountSid")),
            twilio_auth_token=_clean_secret(data.get("twilioAuthToken")),
            twilio_messaging_service_sid=_clean_secret(data.get("twilioMessagingServiceSid")),
            twilio_whatsapp_number=_clean_secret(data.get("twilioWhatsappNumber")),
            twilio_sandbox_mode=bool(data.get("twilioSandboxMode", False)),
        )

    def with_env_defaults(self) -> "IntegrationSettings":
        """Return a copy hydrated with environment fallbacks for missing fields."""
        return IntegrationSettings(
            account_id=self.account_id,
            openai_api_key=self.openai_api_key or os.getenv("OPENAI_API_KEY"),
            openai_org_id=self.openai_org_id or os.getenv("OPENAI_ORG_ID"),
            twilio_account_sid=self.twilio_account_sid or os.getenv("TWILIO_ACCOUNT_SID"),
            twilio_auth_token=self.twilio_auth_token or os.getenv("TWILIO_AUTH_TOKEN"),
            twilio_messaging_service_sid=self.twilio_messaging_service_sid
            or os.getenv("TWILIO_MESSAGING_SERVICE_SID"),
            twilio_whatsapp_number=self.twilio_whatsapp_number or os.getenv("TWILIO_WHATSAPP_NUMBER"),
            twilio_sandbox_mode=self.twilio_sandbox_mode,
        )

    # ------------------------------------------------------------------
    # Convenience flags
    # ------------------------------------------------------------------
    @property
    def openai_ready(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def twilio_ready(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and (
            self.twilio_messaging_service_sid or self.twilio_whatsapp_number
        ))

    @property
    def ready(self) -> bool:
        return self.openai_ready and self.twilio_ready

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------
    def to_firestore(self) -> Dict[str, Any]:
        return {
            "openaiApiKey": self.openai_api_key,
            "openaiOrgId": self.openai_org_id,
            "twilioAccountSid": self.twilio_account_sid,
            "twilioAuthToken": self.twilio_auth_token,
            "twilioMessagingServiceSid": self.twilio_messaging_service_sid,
            "twilioWhatsappNumber": self.twilio_whatsapp_number,
            "twilioSandboxMode": self.twilio_sandbox_mode,
        }

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "ready": self.ready,
            "openai": {
                "ready": self.openai_ready,
                "apiKeyPresent": bool(self.openai_api_key),
                "apiKeyMask": _mask_secret(self.openai_api_key, keep_start=3, keep_end=4),
                "organizationId": self.openai_org_id,
            },
            "twilio": {
                "ready": self.twilio_ready,
                "accountSidMask": _mask_secret(self.twilio_account_sid, keep_start=4, keep_end=4),
                "authTokenMask": _mask_secret(self.twilio_auth_token, keep_start=2, keep_end=2),
                "messagingServiceSidMask": _mask_secret(
                    self.twilio_messaging_service_sid, keep_start=4, keep_end=4
                ),
                "whatsappFrom": self.twilio_whatsapp_number,
                "sandboxMode": self.twilio_sandbox_mode,
            },
        }


# ---------------------------------------------------------------------------
# Store wrapper
# ---------------------------------------------------------------------------
class IntegrationSettingsStore:
    """Read/write helper with a short-lived in-memory cache."""

    def __init__(self) -> None:
        self._client: Optional[firestore.Client] = None
        self._cache: Dict[str, tuple[IntegrationSettings, float]] = {}
        self._ttl_seconds = 30

    def _firestore(self) -> firestore.Client:
        if self._client is None:
            self._client = firestore.client(app=_get_firebase_app())
        return self._client

    def _doc_ref(self, account_id: str):
        return (
            self._firestore().collection("accounts")
            .document(account_id)
            .collection("settings")
            .document("integrations")
        )

    def get(self, account_id: str, *, bypass_cache: bool = False) -> IntegrationSettings:
        now = time.time()
        if not bypass_cache and account_id in self._cache:
            settings, cached_at = self._cache[account_id]
            if now - cached_at < self._ttl_seconds:
                return settings

        snapshot = self._doc_ref(account_id).get()
        settings = IntegrationSettings.from_firestore(account_id, snapshot.to_dict() if snapshot.exists else {})
        self._cache[account_id] = (settings, now)
        return settings

    def update(self, account_id: str, payload: Dict[str, Any]) -> IntegrationSettings:
        current = self.get(account_id, bypass_cache=True)
        data = current.to_firestore()

        def _maybe_update(field: str, key: str) -> None:
            if key not in payload:
                return
            data[field] = _clean_secret(payload.get(key))

        _maybe_update("openaiApiKey", "openaiApiKey")
        _maybe_update("openaiOrgId", "openaiOrgId")
        _maybe_update("twilioAccountSid", "twilioAccountSid")
        _maybe_update("twilioAuthToken", "twilioAuthToken")
        _maybe_update("twilioMessagingServiceSid", "twilioMessagingServiceSid")
        _maybe_update("twilioWhatsappNumber", "twilioWhatsappNumber")

        if "twilioSandboxMode" in payload:
            data["twilioSandboxMode"] = bool(payload.get("twilioSandboxMode"))
        else:
            data["twilioSandboxMode"] = current.twilio_sandbox_mode

        updated = IntegrationSettings.from_firestore(account_id, data)
        self._doc_ref(account_id).set(updated.to_firestore(), merge=True)
        self._cache[account_id] = (updated, time.time())
        return updated


integration_settings_store = IntegrationSettingsStore()
