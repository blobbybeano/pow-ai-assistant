"""Conversation state management for WhatsApp/Twilio interactions."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _utc_now() -> str:
    """Return the current UTC timestamp as an ISO formatted string."""

    return datetime.now(tz=timezone.utc).isoformat()


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "author": self.author,
            "direction": self.direction,
            "timestamp": self.timestamp,
            "via": self.via,
            "transportSid": self.transport_sid,
        }


@dataclass
class ConversationRecord:
    """Represents a full conversation thread."""

    id: str
    phone_number: str
    contact_name: Optional[str] = None
    ai_enabled: bool = True
    unread_count: int = 0
    messages: List[MessageRecord] = field(default_factory=list)

    def last_message(self) -> Optional[MessageRecord]:
        return self.messages[-1] if self.messages else None

    def to_summary(self) -> Dict[str, Any]:
        last_msg = self.last_message()
        return {
            "id": self.id,
            "phoneNumber": self.phone_number,
            "displayName": self.contact_name or self.phone_number,
            "aiEnabled": self.ai_enabled,
            "unreadCount": self.unread_count,
            "lastMessage": last_msg.to_dict() if last_msg else None,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "phoneNumber": self.phone_number,
            "displayName": self.contact_name or self.phone_number,
            "aiEnabled": self.ai_enabled,
            "unreadCount": self.unread_count,
            "messages": [message.to_dict() for message in self.messages],
        }


class ConversationStore:
    """Persistent storage for WhatsApp conversations handled by the webhook."""

    def __init__(self, state_path: Path) -> None:
        self._state_path = state_path
        self._lock = Lock()
        self._conversations: Dict[str, ConversationRecord] = {}
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

        for convo_id, record in payload.get("conversations", {}).items():
            self._conversations[convo_id] = ConversationRecord(
                id=convo_id,
                phone_number=record.get("phoneNumber", convo_id),
                contact_name=record.get("displayName"),
                ai_enabled=record.get("aiEnabled", True),
                unread_count=record.get("unreadCount", 0),
                messages=[
                    MessageRecord(
                        id=msg.get("id", str(uuid4())),
                        text=msg.get("text", ""),
                        author=msg.get("author", "customer"),
                        direction=msg.get("direction", "inbound"),
                        timestamp=msg.get("timestamp", _utc_now()),
                        via=msg.get("via", "whatsapp"),
                        transport_sid=msg.get("transportSid"),
                    )
                    for msg in record.get("messages", [])
                ],
            )

        if not self._conversations:
            self._seed_demo_conversations()
            self._persist()

    def _persist(self) -> None:
        data = {
            "conversations": {
                convo_id: convo.to_dict()
                for convo_id, convo in self._conversations.items()
            }
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
                    key=lambda c: c.last_message().timestamp if c.last_message() else "",
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
        self, conversation_id: str, *, profile_name: Optional[str], phone_number: str
    ) -> ConversationRecord:
        with self._lock:
            convo = self._conversations.get(conversation_id)
            updated = False
            if not convo:
                convo = ConversationRecord(
                    id=conversation_id,
                    phone_number=phone_number,
                    contact_name=profile_name,
                )
                self._conversations[conversation_id] = convo
                updated = True
            else:
                if profile_name and not convo.contact_name:
                    convo.contact_name = profile_name
                    updated = True

            if updated:
                self._persist()
            return convo

    def set_ai_enabled(self, conversation_id: str, enabled: bool) -> bool:
        with self._lock:
            convo = self._conversations.setdefault(
                conversation_id,
                ConversationRecord(id=conversation_id, phone_number=conversation_id),
            )
            convo.ai_enabled = enabled
            self._persist()
            return convo.ai_enabled

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
        increment_unread: bool = False,
    ) -> MessageRecord:
        convo = self.ensure_conversation(
            conversation_id,
            profile_name=profile_name,
            phone_number=conversation_id,
        )

        message = MessageRecord(
            id=str(uuid4()),
            text=text,
            author=author,
            direction=direction,
            timestamp=_utc_now(),
            via=via,
            transport_sid=transport_sid,
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

        demo_threads = {
            "+15551230001": {
                "displayName": "Alex Martinez",
                "aiEnabled": True,
                "messages": [
                    (
                        "customer",
                        "inbound",
                        "Hey PowWash! Can I get pricing for a full patio wash this weekend?",
                    ),
                    (
                        "ai",
                        "outbound",
                        "Hi Alex! A full patio wash starts at $180. Would you like me to reserve a Saturday afternoon slot?",
                    ),
                    (
                        "customer",
                        "inbound",
                        "That sounds great. Let's do 2pm if it's available.",
                    ),
                    (
                        "ai",
                        "outbound",
                        "2pm this Saturday is open. I'll pencil you in and send a confirmation shortly!",
                    ),
                ],
            },
            "+15551230002": {
                "displayName": "Jordan Lee",
                "aiEnabled": False,
                "messages": [
                    (
                        "customer",
                        "inbound",
                        "Can someone help with a quote for cleaning 3 storefront windows?",
                    ),
                    (
                        "system",
                        "outbound",
                        "Thanks for reaching out! A PowWash specialist will reply shortly.",
                    ),
                ],
            },
        }

        for phone, payload in demo_threads.items():
            convo = ConversationRecord(
                id=phone,
                phone_number=phone,
                contact_name=payload.get("displayName"),
                ai_enabled=payload.get("aiEnabled", True),
                unread_count=1,
            )

            for author, direction, text in payload.get("messages", []):
                convo.messages.append(
                    MessageRecord(
                        id=str(uuid4()),
                        text=text,
                        author=author,
                        direction=direction,
                        timestamp=_utc_now(),
                    )
                )

            self._conversations[phone] = convo


# Convenience singleton -------------------------------------------------------

_STORE_PATH = Path("conversation_state.json")
conversation_store = ConversationStore(_STORE_PATH)

