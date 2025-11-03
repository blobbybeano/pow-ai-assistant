"""Utilities for sending outbound WhatsApp messages via Twilio."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple

import httpx
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client


@dataclass
class TwilioConfig:
    account_sid: str
    auth_token: str
    whatsapp_from: Optional[str] = None
    messaging_service_sid: Optional[str] = None


class TwilioMessenger:
    """Wrapper around the Twilio REST client for WhatsApp sending."""

    def __init__(self, config: TwilioConfig) -> None:
        self._config = config
        self._client = Client(config.account_sid, config.auth_token)

    @classmethod
    def from_env(cls) -> Optional["TwilioMessenger"]:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")

        if not account_sid or not auth_token:
            return None

        whatsapp_from = _normalize_whatsapp_address(os.getenv("TWILIO_WHATSAPP_NUMBER"))

        messaging_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")

        config = TwilioConfig(
            account_sid=account_sid,
            auth_token=auth_token,
            whatsapp_from=whatsapp_from,
            messaging_service_sid=messaging_service_sid,
        )

        return cls(config)

    def send_whatsapp_message(self, *, to: str, body: str) -> str:
        if not body.strip():
            raise ValueError("Message body cannot be empty.")

        to_address = _normalize_whatsapp_address(to)
        if not to_address:
            raise ValueError("Recipient phone number is invalid.")

        kwargs = {"to": to_address, "body": body}

        if self._config.messaging_service_sid:
            kwargs["messaging_service_sid"] = self._config.messaging_service_sid
        elif self._config.whatsapp_from:
            kwargs["from_"] = self._config.whatsapp_from
        else:
            raise RuntimeError(
                "Configure TWILIO_WHATSAPP_NUMBER or TWILIO_MESSAGING_SERVICE_SID to send messages."
            )

        try:
            message = self._client.messages.create(**kwargs)
        except TwilioRestException as exc:  # pragma: no cover - network side
            raise RuntimeError(f"Failed to send WhatsApp message: {exc.msg}") from exc

        return message.sid

    def fetch_media(self, url: str) -> Tuple[bytes, str]:
        """Download a media asset from Twilio and return its bytes and content type."""

        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                url,
                auth=(self._config.account_sid, self._config.auth_token),
                follow_redirects=True,
            )
            response.raise_for_status()

        content_type = response.headers.get("Content-Type", "application/octet-stream")
        return response.content, content_type


def _normalize_whatsapp_address(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    raw = value.strip()
    if not raw:
        return None

    if raw.lower().startswith("whatsapp:"):
        raw = raw.split(":", 1)[1]

    raw = raw.replace(" ", "")

    if raw.startswith("+"):
        digits = "+" + re.sub(r"[^\d]", "", raw[1:])
    elif raw.startswith("00"):
        digits_only = re.sub(r"[^\d]", "", raw[2:])
        digits = f"+{digits_only}" if digits_only else ""
    else:
        digits_only = re.sub(r"[^\d]", "", raw)
        digits = f"+{digits_only}" if digits_only else ""

    if not digits or digits == "+":
        return None

    return f"whatsapp:{digits}"
