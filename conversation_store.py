"""Conversation state management for WhatsApp/Twilio interactions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4

from urllib.parse import quote_plus


def _utc_now() -> str:
    """Return the current UTC timestamp as an ISO formatted string."""

    return datetime.now(tz=timezone.utc).isoformat()


_AVATAR_BACKGROUNDS = (
    "0D8ABC",
    "F4A261",
    "2A9D8F",
    "E76F51",
    "8ECAE6",
)


def _generate_avatar(profile_name: Optional[str], phone_number: str) -> str:
    """Return a deterministic avatar URL for a contact."""

    base = (profile_name or phone_number or "PowWash").strip()
    if not base:
        base = phone_number or "PowWash"
    encoded = quote_plus(base)
    digest = hashlib.sha1(base.encode("utf-8")).digest()
    color_index = digest[0] % len(_AVATAR_BACKGROUNDS)
    color = _AVATAR_BACKGROUNDS[color_index]
    return f"https://ui-avatars.com/api/?name={encoded}&background={color}&color=ffffff"


def _is_placeholder_avatar(url: Optional[str]) -> bool:
    if not url:
        return False
    return url.startswith("https://ui-avatars.com/")


@dataclass
class MessageRecord:
    """Represents a single chat message stored in the conversation history."""

    id: str
    text: str
    author: str  # customer | ai | agent | system
    direction: str  # inbound | outbound
    timestamp: str
    via: str = "whatsapp"
    transport_sid: Optional[str] = None
    status: str = (
        "sent"  # sent | scheduled | failed | draft | sending | drafting | cancelled
    )
    scheduled_send_at: Optional[str] = None
    sent_at: Optional[str] = None
    error: Optional[str] = None
    attachments: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "author": self.author,
            "direction": self.direction,
            "timestamp": self.timestamp,
            "via": self.via,
            "transportSid": self.transport_sid,
            "status": self.status,
            "scheduledSendAt": self.scheduled_send_at,
            "sentAt": self.sent_at,
            "error": self.error,
            "attachments": list(self.attachments),
        }

    def effective_datetime(self) -> datetime:
        """Return the best timestamp to represent this message chronologically."""

        for candidate in (self.sent_at, self.scheduled_send_at, self.timestamp):
            if candidate:
                try:
                    return datetime.fromisoformat(candidate)
                except ValueError:
                    continue
        # Fallback to now if parsing fails
        return datetime.now(tz=timezone.utc)


@dataclass
class ConversationRecord:
    """Represents a full conversation thread."""

    id: str
    phone_number: str
    contact_name: Optional[str] = None
    contact_photo_url: Optional[str] = None
    ai_enabled: bool = True
    unread_count: int = 0
    assigned_responder_id: Optional[str] = None
    messages: List[MessageRecord] = field(default_factory=list)

    def last_message(self) -> Optional[MessageRecord]:
        return self.messages[-1] if self.messages else None

    def to_summary(self) -> Dict[str, Any]:
        last_msg = self.last_message()
        return {
            "id": self.id,
            "phoneNumber": self.phone_number,
            "displayName": self.contact_name or self.phone_number,
            "profilePhotoUrl": self.contact_photo_url,
            "aiEnabled": self.ai_enabled,
            "unreadCount": self.unread_count,
            "assignedResponderId": self.assigned_responder_id,
            "lastMessage": last_msg.to_dict() if last_msg else None,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "phoneNumber": self.phone_number,
            "displayName": self.contact_name or self.phone_number,
            "profilePhotoUrl": self.contact_photo_url,
            "aiEnabled": self.ai_enabled,
            "unreadCount": self.unread_count,
            "assignedResponderId": self.assigned_responder_id,
            "messages": [message.to_dict() for message in self.messages],
        }


class ConversationStore:
    """Persistent storage for WhatsApp conversations handled by the webhook."""

    def __init__(self, state_path: Path, *, seed_demo: bool = True) -> None:
        self._state_path = state_path
        self._lock = Lock()
        self._conversations: Dict[str, ConversationRecord] = {}
        self._settings: Dict[str, Any] = {}
        self._seed_demo = seed_demo
        self._load_state()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _load_state(self) -> None:
        if not self._state_path.exists():
            self._state_path.write_text("{}", encoding="utf-8")
            payload: Dict[str, Any] = {}
        else:
            try:
                payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}

        self._settings = payload.get("settings", {}) if isinstance(payload, dict) else {}

        for convo_id, record in payload.get("conversations", {}).items():
            self._conversations[convo_id] = ConversationRecord(
                id=convo_id,
                phone_number=record.get("phoneNumber", convo_id),
                contact_name=record.get("displayName"),
                contact_photo_url=record.get("profilePhotoUrl"),
                ai_enabled=record.get("aiEnabled", True),
                unread_count=record.get("unreadCount", 0),
                assigned_responder_id=record.get("assignedResponderId"),
                messages=[
                    MessageRecord(
                        id=msg.get("id", str(uuid4())),
                        text=msg.get("text", ""),
                        author=msg.get("author", "customer"),
                        direction=msg.get("direction", "inbound"),
                        timestamp=msg.get("timestamp", _utc_now()),
                        via=msg.get("via", "whatsapp"),
                        transport_sid=msg.get("transportSid"),
                        status=msg.get("status", "sent"),
                        scheduled_send_at=msg.get("scheduledSendAt"),
                        sent_at=msg.get("sentAt"),
                        error=msg.get("error"),
                        attachments=[
                            attachment
                            for attachment in msg.get("attachments", [])
                            if isinstance(attachment, str)
                        ],
                    )
                    for msg in record.get("messages", [])
                ],
            )

            convo = self._conversations[convo_id]
            if not convo.contact_photo_url:
                convo.contact_photo_url = _generate_avatar(
                    convo.contact_name, convo.phone_number
                )

        if not self._conversations and self._seed_demo:
            self._seed_demo_conversations()
            self._persist()

    def _persist(self) -> None:
        data = {
            "settings": self._settings,
            "conversations": {
                convo_id: convo.to_dict()
                for convo_id, convo in self._conversations.items()
            },
        }
        self._state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_conversations(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                convo.to_summary()
                for convo in sorted(
                    self._conversations.values(),
                    key=lambda c: (
                        c.last_message().effective_datetime()
                        if c.last_message()
                        else datetime.fromtimestamp(0, tz=timezone.utc)
                    ),
                    reverse=True,
                )
            ]

    def get_conversation(
        self, conversation_id: str, *, mark_read: bool = False
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            convo = self._conversations.get(conversation_id)
            if not convo:
                return None

            if mark_read:
                convo.unread_count = 0
                self._persist()

            return convo.to_dict()

    def ensure_conversation(
        self,
        conversation_id: str,
        *,
        profile_name: Optional[str],
        phone_number: str,
        profile_photo_url: Optional[str] = None,
    ) -> ConversationRecord:
        with self._lock:
            convo = self._conversations.get(conversation_id)
            updated = False
            if not convo:
                avatar = profile_photo_url or _generate_avatar(
                    profile_name, phone_number
                )
                convo = ConversationRecord(
                    id=conversation_id,
                    phone_number=phone_number,
                    contact_name=profile_name,
                    contact_photo_url=avatar,
                    assigned_responder_id=self.default_responder_id,
                )
                self._conversations[conversation_id] = convo
                updated = True
            else:
                if profile_name and not convo.contact_name:
                    convo.contact_name = profile_name
                    updated = True
                    if _is_placeholder_avatar(convo.contact_photo_url):
                        convo.contact_photo_url = _generate_avatar(
                            profile_name, phone_number
                        )

                trimmed_photo = (profile_photo_url or "").strip() or None
                if trimmed_photo and trimmed_photo != convo.contact_photo_url:
                    convo.contact_photo_url = trimmed_photo
                    updated = True
                elif not convo.contact_photo_url:
                    convo.contact_photo_url = _generate_avatar(
                        convo.contact_name, phone_number
                    )
                    updated = True

                if not convo.assigned_responder_id and self.default_responder_id:
                    convo.assigned_responder_id = self.default_responder_id
                    updated = True

            if updated:
                self._persist()
            return convo

    def set_ai_enabled(self, conversation_id: str, enabled: bool) -> bool:
        with self._lock:
            convo = self._conversations.setdefault(
                conversation_id,
                ConversationRecord(
                    id=conversation_id,
                    phone_number=conversation_id,
                    assigned_responder_id=self.default_responder_id,
                ),
            )
            convo.ai_enabled = enabled
            self._persist()
            return convo.ai_enabled

    @property
    def default_responder_id(self) -> Optional[str]:
        value = self._settings.get("defaultResponderId")
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        return None

    def set_default_responder(self, responder_id: Optional[str]) -> None:
        with self._lock:
            trimmed = (responder_id or "").strip()
            if trimmed:
                self._settings["defaultResponderId"] = trimmed
            else:
                self._settings.pop("defaultResponderId", None)
            self._persist()

    def assign_conversation(
        self, conversation_id: str, responder_id: Optional[str]
    ) -> Optional[str]:
        if responder_id is None:
            return None
        responder = responder_id.strip()
        if not responder:
            return None
        with self._lock:
            convo = self._conversations.get(conversation_id)
            if not convo:
                convo = ConversationRecord(
                    id=conversation_id,
                    phone_number=conversation_id,
                    assigned_responder_id=responder,
                )
                self._conversations[conversation_id] = convo
            if convo.assigned_responder_id == responder:
                return responder
            convo.assigned_responder_id = responder
            self._persist()
            return responder

    def record_message(
        self,
        conversation_id: str,
        *,
        text: str,
        author: str,
        direction: str,
        via: str = "whatsapp",
        transport_sid: Optional[str] = None,
        profile_name: Optional[str] = None,
        profile_photo_url: Optional[str] = None,
        increment_unread: bool = False,
        status: str = "sent",
        scheduled_send_at: Optional[str] = None,
        sent_at: Optional[str] = None,
        error: Optional[str] = None,
        attachments: Optional[List[str]] = None,
    ) -> MessageRecord:
        convo = self.ensure_conversation(
            conversation_id,
            profile_name=profile_name,
            phone_number=conversation_id,
            profile_photo_url=profile_photo_url,
        )

        message = MessageRecord(
            id=str(uuid4()),
            text=text,
            author=author,
            direction=direction,
            timestamp=_utc_now(),
            via=via,
            transport_sid=transport_sid,
            status=status,
            scheduled_send_at=scheduled_send_at,
            sent_at=sent_at,
            error=error,
            attachments=list(attachments or []),
        )

        with self._lock:
            convo.messages.append(message)
            if increment_unread:
                convo.unread_count += 1
            self._persist()

        return message

    def latest_customer_message(self, conversation_id: str) -> Optional[MessageRecord]:
        with self._lock:
            convo = self._conversations.get(conversation_id)
            if not convo:
                return None

            for message in reversed(convo.messages):
                if message.author == "customer":
                    return message
        return None

    # ------------------------------------------------------------------
    # Demo data
    # ------------------------------------------------------------------
    def _seed_demo_conversations(self) -> None:
        """Populate the store with demo conversations for first-time setup."""

        demo_threads = [
            {
                "phone": "+15551230001",
                "displayName": "Alex Martinez",
                "profilePhotoUrl": "https://ui-avatars.com/api/?name=Alex+Martinez&background=0D8ABC&color=ffffff",
                "aiEnabled": True,
                "unreadCount": 1,
                "assignedResponderId": "user-1",
                "messages": [
                    {
                        "author": "customer",
                        "direction": "inbound",
                        "text": "Good morning! I'd like to get a quote for driveway cleaning next week.",
                    },
                    {
                        "author": "ai",
                        "direction": "outbound",
                        "text": "Hi Alex! A driveway refresh for two cars starts at $150, and includes a degreasing pre-soak and rinse. Do you have a preferred day next week?",
                    },
                    {
                        "author": "customer",
                        "direction": "inbound",
                        "text": "Could you do Friday at 10am? I can send photos if helpful.",
                    },
                ],
            },
            {
                "phone": "+14085550100",
                "displayName": "Jordan Lee",
                "profilePhotoUrl": "https://ui-avatars.com/api/?name=Jordan+Lee&background=2A9D8F&color=ffffff",
                "aiEnabled": False,
                "unreadCount": 1,
                "assignedResponderId": "user-2",
                "messages": [
                    {
                        "author": "customer",
                        "direction": "inbound",
                        "text": "Our café patio is getting slippery. Can you fit us in for a wash this Thursday?",
                    },
                    {
                        "author": "ai",
                        "direction": "outbound",
                        "text": "Hi Jordan! We can usually fit patio treatments within 48 hours. Does late morning Thursday work for you?",
                    },
                    {
                        "author": "customer",
                        "direction": "inbound",
                        "text": "Late morning works, thanks!",
                    },
                ],
            },
            {
                "phone": "+447700900123",
                "displayName": "Priya Sharma",
                "profilePhotoUrl": "https://ui-avatars.com/api/?name=Priya+Sharma&background=F4A261&color=ffffff",
                "aiEnabled": True,
                "unreadCount": 0,
                "assignedResponderId": "user-3",
                "messages": [
                    {
                        "author": "customer",
                        "direction": "inbound",
                        "text": "Hello! Looking for gutter cleaning for a two-storey semi-detached.",
                    },
                    {
                        "author": "ai",
                        "direction": "outbound",
                        "text": "Hi Priya! A two-storey gutter clear is £95 and includes a downpipe flush and photo report. Want me to pencil you in for next week?",
                    },
                    {
                        "author": "customer",
                        "direction": "inbound",
                        "text": "Yes please, any availability on Tuesday morning?",
                    },
                    {
                        "author": "ai",
                        "direction": "outbound",
                        "text": "Tuesday at 9am is open. I'll schedule the crew and send you a confirmation shortly!",
                        "status": "scheduled",
                        "scheduled_in_seconds": 240,
                    },
                ],
            },
            {
                "phone": "+16175550123",
                "displayName": "Taylor Chen",
                "profilePhotoUrl": "https://ui-avatars.com/api/?name=Taylor+Chen&background=8ECAE6&color=ffffff",
                "aiEnabled": True,
                "unreadCount": 1,
                "assignedResponderId": "user-4",
                "messages": [
                    {
                        "author": "customer",
                        "direction": "inbound",
                        "text": "Could you quote a roof softwash for a 1,600 sq ft home?",
                    },
                    {
                        "author": "ai",
                        "direction": "outbound",
                        "text": "Hi Taylor! A roof softwash for that size starts at $420 and includes plant-safe pretreatment. Would you like me to arrange a site visit?",
                    },
                    {
                        "author": "customer",
                        "direction": "inbound",
                        "text": "Yes, please schedule something next week.",
                    },
                ],
            },
        ]

        now = datetime.now(timezone.utc)
        for payload in demo_threads:
            phone = payload["phone"]
            convo = ConversationRecord(
                id=phone,
                phone_number=phone,
                contact_name=payload.get("displayName"),
                contact_photo_url=payload.get("profilePhotoUrl")
                or _generate_avatar(payload.get("displayName"), phone),
                ai_enabled=payload.get("aiEnabled", True),
                unread_count=payload.get("unreadCount", 0),
                assigned_responder_id=payload.get("assignedResponderId"),
            )

            message_time = now
            for message_payload in payload.get("messages", []):
                message_time += timedelta(seconds=30)
                status = message_payload.get("status", "sent")
                scheduled_send_at: Optional[str] = None
                sent_at: Optional[str] = message_time.isoformat()
                if status == "scheduled":
                    delay = message_payload.get("scheduled_in_seconds", 180)
                    scheduled_send_at = (message_time + timedelta(seconds=delay)).isoformat()
                    sent_at = None

                convo.messages.append(
                    MessageRecord(
                        id=str(uuid4()),
                        text=message_payload["text"],
                        author=message_payload["author"],
                        direction=message_payload["direction"],
                        timestamp=message_time.isoformat(),
                        sent_at=sent_at,
                        status=status,
                        scheduled_send_at=scheduled_send_at,
                    )
                )

            self._conversations[phone] = convo

        if "defaultResponderId" not in self._settings:
            self._settings["defaultResponderId"] = "user-1"

    def pending_scheduled_messages(self) -> List[tuple[str, MessageRecord]]:
        """Return copies of AI messages that are scheduled for delivery."""

        with self._lock:
            pending: List[tuple[str, MessageRecord]] = []
            for convo in self._conversations.values():
                for message in convo.messages:
                    if message.author == "ai" and message.status == "scheduled":
                        pending.append(
                            (
                                convo.id,
                                MessageRecord(
                                    id=message.id,
                                    text=message.text,
                                    author=message.author,
                                    direction=message.direction,
                                    timestamp=message.timestamp,
                                    via=message.via,
                                    transport_sid=message.transport_sid,
                                    status=message.status,
                                    scheduled_send_at=message.scheduled_send_at,
                                    sent_at=message.sent_at,
                                    error=message.error,
                                ),
                            )
                        )
            return pending

    def get_message(
        self, conversation_id: str, message_id: str
    ) -> Optional[MessageRecord]:
        """Return a specific message from a conversation without mutating state."""

        with self._lock:
            convo = self._conversations.get(conversation_id)
            if not convo:
                return None

            for message in convo.messages:
                if message.id == message_id:
                    return MessageRecord(
                        id=message.id,
                        text=message.text,
                        author=message.author,
                        direction=message.direction,
                        timestamp=message.timestamp,
                        via=message.via,
                        transport_sid=message.transport_sid,
                        status=message.status,
                        scheduled_send_at=message.scheduled_send_at,
                        sent_at=message.sent_at,
                        error=message.error,
                        attachments=list(message.attachments),
                    )

        return None

    def update_message(
        self,
        conversation_id: str,
        message_id: str,
        *,
        text: Optional[str] = None,
        status: Optional[str] = None,
        sent_at: Optional[str] = None,
        transport_sid: Optional[str] = None,
        error: Optional[str] = None,
        scheduled_send_at: Optional[str] = None,
        attachments: Optional[List[str]] = None,
    ) -> Optional[MessageRecord]:
        """Update a specific message record and persist the store."""

        with self._lock:
            convo = self._conversations.get(conversation_id)
            if not convo:
                return None

            for message in convo.messages:
                if message.id == message_id:
                    if text is not None:
                        message.text = text
                    if status is not None:
                        message.status = status
                    if sent_at is not None:
                        message.sent_at = sent_at
                    if transport_sid is not None:
                        message.transport_sid = transport_sid
                    if error is not None:
                        message.error = error
                    if scheduled_send_at is not None:
                        message.scheduled_send_at = scheduled_send_at
                    if attachments is not None:
                        message.attachments = list(attachments)
                    self._persist()
                    return message

        return None

    def cancel_scheduled_message(
        self, conversation_id: str, message_id: str
    ) -> Optional[MessageRecord]:
        """Mark a scheduled AI message as cancelled."""

        with self._lock:
            convo = self._conversations.get(conversation_id)
            if not convo:
                return None

            for message in convo.messages:
                if message.id == message_id and message.author == "ai":
                    if message.status not in {"scheduled", "drafting"}:
                        return None
                    message.status = "cancelled"
                    message.scheduled_send_at = None
                    message.error = "Cancelled by agent"
                    self._persist()
                    return message

        return None

    def cancel_pending_ai_messages(
        self, conversation_id: str, *, reason: Optional[str] = None
    ) -> List[str]:
        """Cancel all scheduled or drafting AI messages for a conversation."""

        with self._lock:
            convo = self._conversations.get(conversation_id)
            if not convo:
                return []

            explanation = (reason or "Cancelled by agent").strip() or "Cancelled by agent"
            cancelled_ids: List[str] = []

            for message in convo.messages:
                if message.author == "ai" and message.status in {"scheduled", "drafting"}:
                    message.status = "cancelled"
                    message.scheduled_send_at = None
                    message.error = explanation
                    cancelled_ids.append(message.id)

            if cancelled_ids:
                self._persist()

            return cancelled_ids


# Convenience singleton -------------------------------------------------------

_STORE_PATH = Path("conversation_state.json")
conversation_store = ConversationStore(_STORE_PATH)
