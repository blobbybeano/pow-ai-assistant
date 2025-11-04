"""Utilities for loading optional workspace configuration overrides."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

_DEFAULT_CONFIG_PATH = Path("workspace_settings.json")


@dataclass
class TwilioSettings:
    """Strongly typed view of Twilio-related configuration."""

    account_sid: Optional[str] = None
    auth_token: Optional[str] = None
    whatsapp_number: Optional[str] = None
    messaging_service_sid: Optional[str] = None
    webhook_url: Optional[str] = None


@dataclass
class ApiSettings:
    """Optional overrides for the public API exposed to clients."""

    base_url: Optional[str] = None


@dataclass
class WorkspaceSettings:
    """Container for all optional workspace configuration values."""

    api: ApiSettings = field(default_factory=ApiSettings)
    twilio: TwilioSettings = field(default_factory=TwilioSettings)


def _load_raw_settings(path: Path) -> Dict[str, Any]:
    """Read a JSON document from *path* and return it as a dictionary."""

    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        logging.exception("Failed to parse workspace settings from %s", path)
    except OSError:
        logging.exception("Failed to read workspace settings from %s", path)
    return {}


def load_workspace_settings(path: Optional[Path] = None) -> WorkspaceSettings:
    """Load workspace settings from JSON, falling back to sane defaults."""

    target_path = path or _DEFAULT_CONFIG_PATH
    payload = _load_raw_settings(target_path)

    api_settings = payload.get("api", {}) if isinstance(payload, dict) else {}
    twilio_settings = payload.get("twilio", {}) if isinstance(payload, dict) else {}

    return WorkspaceSettings(
        api=ApiSettings(
            base_url=_clean_string(api_settings.get("baseUrl")),
        ),
        twilio=TwilioSettings(
            account_sid=_clean_string(twilio_settings.get("accountSid")),
            auth_token=_clean_string(twilio_settings.get("authToken")),
            whatsapp_number=_clean_string(twilio_settings.get("whatsappNumber")),
            messaging_service_sid=_clean_string(
                twilio_settings.get("messagingServiceSid")
            ),
            webhook_url=_clean_string(twilio_settings.get("webhookUrl")),
        ),
    )


def _clean_string(value: Any) -> Optional[str]:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed:
            return trimmed
    return None
