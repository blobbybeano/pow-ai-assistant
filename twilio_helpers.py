"""Utilities for sending outbound WhatsApp messages via Twilio.

Supports either Messaging Service SIDs or direct WhatsApp senders so each
account can bring its own credentials.
"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass
from typing import Optional
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client


# ==========================================================
# Configuration data structure
# ==========================================================
@dataclass
class TwilioConfig:
    account_sid: str
    auth_token: str
    messaging_service_sid: Optional[str] = None
    whatsapp_from: Optional[str] = None


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

        if not all([account_sid, auth_token]) or not (messaging_service_sid or os.getenv("TWILIO_WHATSAPP_NUMBER")):
            print("⚠️ Missing Twilio environment variables; messenger not initialized.")
            return None

        config = TwilioConfig(
            account_sid=account_sid,
            auth_token=auth_token,
            messaging_service_sid=messaging_service_sid,
            whatsapp_from=os.getenv("TWILIO_WHATSAPP_NUMBER"),
        )
        return cls(config)

    @classmethod
    def from_settings(
        cls,
        account_sid: str,
        auth_token: str,
        *,
        messaging_service_sid: Optional[str] = None,
        whatsapp_from: Optional[str] = None,
    ) -> Optional["TwilioMessenger"]:
        if not account_sid or not auth_token or not (messaging_service_sid or whatsapp_from):
            return None
        config = TwilioConfig(
            account_sid=account_sid,
            auth_token=auth_token,
            messaging_service_sid=messaging_service_sid,
            whatsapp_from=whatsapp_from,
        )
        return cls(config)

    def send_whatsapp_message(self, *, to: str, body: str) -> str:
        """Send a WhatsApp message using the configured Messaging Service."""
        if not body.strip():
            raise ValueError("Message body cannot be empty.")

        to_address = _normalize_whatsapp_address(to)
        if not to_address:
            raise ValueError("Recipient phone number is invalid.")

        kwargs = {"to": to_address, "body": body}
        if self._config.messaging_service_sid:
            kwargs["messaging_service_sid"] = self._config.messaging_service_sid
            print(f"[TwilioMessenger] Sending via Messaging Service SID: {self._config.messaging_service_sid}")
        elif self._config.whatsapp_from:
            kwargs["from_"] = self._config.whatsapp_from
            print(f"[TwilioMessenger] Sending via WhatsApp number: {self._config.whatsapp_from}")
        else:
            raise RuntimeError("Twilio Messenger is misconfigured: no sender configured.")

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
