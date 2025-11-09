"""
Utilities for sending outbound WhatsApp messages via Twilio.

This version is simplified for Messaging Service use only.
It ignores TWILIO_WHATSAPP_NUMBER entirely.
"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass
from typing import List, Optional
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client


# ==========================================================
# Configuration data structure
# ==========================================================
@dataclass
class TwilioConfig:
    account_sid: str
    auth_token: str
    messaging_service_sid: str


# ==========================================================
# Twilio Messenger class
# ==========================================================
class TwilioMessenger:
    """Wrapper around Twilio REST client for sending WhatsApp messages."""

    def __init__(self, config: TwilioConfig) -> None:
        self._config = config
        self._client = Client(config.account_sid, config.auth_token)

    @classmethod
    def from_env(cls) -> Optional["TwilioMessenger"]:
        """Build a messenger using only Messaging Service credentials."""
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        messaging_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")

        if not all([account_sid, auth_token, messaging_service_sid]):
            print("⚠️ Missing Twilio environment variables; messenger not initialized.")
            return None

        config = TwilioConfig(
            account_sid=account_sid,
            auth_token=auth_token,
            messaging_service_sid=messaging_service_sid,
        )
        return cls(config)

    def send_whatsapp_message(
        self,
        *,
        to: str,
        body: str,
        media_urls: Optional[List[str]] = None,
    ) -> str:
        """Send a WhatsApp message using the configured Messaging Service."""
        if not body.strip() and not media_urls:
            raise ValueError("Message body or media is required.")

        to_address = _normalize_whatsapp_address(to)
        if not to_address:
            raise ValueError("Recipient phone number is invalid.")

        kwargs = {
            "to": to_address,
            "body": body,
            "messaging_service_sid": self._config.messaging_service_sid,
        }

        if media_urls:
            kwargs["media_url"] = media_urls

        print(f"[TwilioMessenger] Sending via Messaging Service SID: {self._config.messaging_service_sid}")
        print(f"[TwilioMessenger] → {to_address}")

        try:
            message = self._client.messages.create(**kwargs)
        except TwilioRestException as exc:
            raise RuntimeError(
                f"Failed to send WhatsApp message: {exc.msg} (status={exc.status}, code={exc.code})"
            ) from exc

        return message.sid


# ==========================================================
# Helper: normalize WhatsApp address
# ==========================================================
def _normalize_whatsapp_address(value: Optional[str]) -> Optional[str]:
    """Normalize input like 07541 088300 → whatsapp:+447541088300"""
    if not value:
        return None

    raw = value.strip().lower()
    if raw.startswith("whatsapp:"):
        raw = raw.split(":", 1)[1]
    raw = re.sub(r"[^\d+]", "", raw)

    if raw.startswith("+"):
        digits = "+" + re.sub(r"[^\d]", "", raw[1:])
    elif raw.startswith("00"):
        digits = "+" + re.sub(r"[^\d]", "", raw[2:])
    elif raw.startswith("0"):
        digits = "+44" + re.sub(r"[^\d]", "", raw[1:])
    elif raw.startswith("44"):
        digits = "+" + re.sub(r"[^\d]", "", raw)
    else:
        digits = "+" + re.sub(r"[^\d]", "", raw)

    return f"whatsapp:{digits}" if digits and digits != "+" else None
