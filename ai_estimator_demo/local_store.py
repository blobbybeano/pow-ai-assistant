"""File-backed conversation store — no Firebase required.

Persists all conversations and messages to conversations_local.json inside the
app directory.  Thread-safe.  Used whenever Firestore is not configured.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

from pg_store import PersistentFile

_APP_ROOT = Path(__file__).parent
# Postgres-backed so conversation history survives Autoscale deploys/restarts
# and is shared across instances. Falls back to the local file automatically
# when DATABASE_URL is not set.
_STORE_PATH = PersistentFile(_APP_ROOT / "conversations_local.json")


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(dt) -> Optional[str]:
    if isinstance(dt, datetime):
        return dt.isoformat()
    if isinstance(dt, str):
        return dt
    return None


class LocalConversationStore:
    """JSON-file backed store with the same public API as the Firestore store."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> Dict[str, Any]:
        try:
            if _STORE_PATH.exists():
                return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("local_store: could not read %s: %s", _STORE_PATH, exc)
        return {}

    def _save(self) -> None:
        try:
            _STORE_PATH.write_text(json.dumps(self._data, indent=2, default=str), encoding="utf-8")
        except Exception as exc:
            logger.warning("local_store: could not write %s: %s", _STORE_PATH, exc)

    def _refresh(self) -> None:
        """Re-read from the backing store (Postgres) so this worker sees writes
        made by other Autoscale instances. Must be called while holding the lock
        (RLock makes nested acquisition safe)."""
        self._data = self._load()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _convo(self, cid: str) -> Dict[str, Any]:
        """Return existing conversation bucket or create a fresh one."""
        if cid not in self._data:
            self._data[cid] = {
                "id": cid,
                "phoneNumber": cid,
                "displayName": cid,
                "aiEnabled": True,
                "unreadCount": 0,
                "lastMessageAt": None,
                "lastMessage": None,
                "messages": [],
            }
        return self._data[cid]

    # ── Public API ────────────────────────────────────────────────────────────

    def list_conversations(self, account_id=None) -> List[Dict[str, Any]]:
        with self._lock:
            self._refresh()
            convos = list(self._data.values())

        def _sort_key(c):
            t = c.get("lastMessageAt")
            return t or ""

        convos.sort(key=_sort_key, reverse=True)
        return [
            {
                "id": c["id"],
                "phoneNumber": c["phoneNumber"],
                "displayName": c.get("displayName") or c["phoneNumber"],
                "profilePhotoUrl": c.get("profilePhotoUrl"),
                "aiEnabled": c.get("aiEnabled", True),
                "unreadCount": c.get("unreadCount", 0),
                "assignedResponderId": c.get("assignedResponderId"),
                "lastMessage": c.get("lastMessage"),
            }
            for c in convos
        ]

    def get_conversation(self, account_id=None, conversation_id: str = "", *, mark_read: bool = False) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._refresh()
            if conversation_id not in self._data:
                return None
            c = self._data[conversation_id]
            if mark_read:
                c["unreadCount"] = 0
                self._save()
            return {
                "id": c["id"],
                "phoneNumber": c["phoneNumber"],
                "displayName": c.get("displayName") or c["phoneNumber"],
                "profilePhotoUrl": c.get("profilePhotoUrl"),
                "aiEnabled": c.get("aiEnabled", True),
                "unreadCount": c.get("unreadCount", 0),
                "assignedResponderId": c.get("assignedResponderId"),
                "messages": list(c.get("messages", [])),
            }

    def record_message(
        self,
        account_id=None,
        conversation_id: str = "",
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
        scheduled_send_at=None,
        sent_at=None,
        error: Optional[str] = None,
        attachments: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        now = _utc_now()
        msg = {
            "id": str(uuid4()),
            "text": text,
            "author": author,
            "direction": direction,
            "timestamp": _iso(now),
            "via": via,
            "transportSid": transport_sid,
            "status": status,
            "scheduledSendAt": _iso(scheduled_send_at),
            "sentAt": _iso(sent_at or now),
            "error": error,
            "attachments": list(attachments or []),
        }
        with self._lock:
            self._refresh()
            c = self._convo(conversation_id)
            if profile_name and not c.get("displayName"):
                c["displayName"] = profile_name
            if profile_name:
                c["displayName"] = profile_name
            if profile_photo_url:
                c["profilePhotoUrl"] = profile_photo_url
            if increment_unread:
                c["unreadCount"] = c.get("unreadCount", 0) + 1
            c["messages"].append(msg)
            c["lastMessage"] = msg
            c["lastMessageAt"] = _iso(now)
            self._save()
        return msg

    def set_ai_enabled(self, account_id=None, conversation_id: str = "", enabled: bool = True) -> bool:
        with self._lock:
            self._refresh()
            c = self._convo(conversation_id)
            c["aiEnabled"] = enabled
            self._save()
        return enabled

    def cancel_pending_ai_messages(self, account_id=None, conversation_id: str = "", reason: str = "") -> int:
        cancelled = 0
        with self._lock:
            self._refresh()
            if conversation_id in self._data:
                for msg in self._data[conversation_id].get("messages", []):
                    if msg.get("author") == "ai" and msg.get("status") in ("scheduled", "drafting"):
                        msg["status"] = "cancelled"
                        msg["error"] = reason
                        cancelled += 1
                if cancelled:
                    self._save()
        return cancelled

    def get_pending_ai_messages(self, account_id=None, conversation_id: str = "") -> List[Dict[str, Any]]:
        with self._lock:
            self._refresh()
            if conversation_id not in self._data:
                return []
            return [
                m for m in self._data[conversation_id].get("messages", [])
                if m.get("author") == "ai" and m.get("status") in ("scheduled", "drafting")
            ]

    def latest_customer_message(self, account_id=None, conversation_id: str = "") -> Optional[Dict[str, Any]]:
        with self._lock:
            self._refresh()
            if conversation_id not in self._data:
                return None
            msgs = [m for m in self._data[conversation_id].get("messages", [])
                    if m.get("author") == "customer"]
            return msgs[-1] if msgs else None

    def store_ai_draft(self, account_id=None, conversation_id: str = "", draft_text: str = "", send_at=None) -> Dict[str, Any]:
        return self.record_message(
            account_id, conversation_id,
            text=draft_text, author="ai", direction="outbound",
            status="scheduled", scheduled_send_at=send_at,
        )

    def cancel_scheduled_message(self, account_id=None, conversation_id: str = "", message_id: str = "") -> Optional[Dict[str, Any]]:
        """Mark a specific scheduled AI message as cancelled.
        Returns the message only if we actually changed its status to 'cancelled'.
        Returns None if not found OR if the message was already in a non-cancellable state
        (e.g. already sent or already cancelled by another path).
        Callers must treat None as 'do not proceed' to prevent double-sends.
        """
        with self._lock:
            self._refresh()
            if conversation_id not in self._data:
                return None
            for msg in self._data[conversation_id].get("messages", []):
                if msg.get("id") == message_id:
                    if msg.get("status") in ("scheduled", "drafting"):
                        msg["status"] = "cancelled"
                        self._save()
                        return msg
                    return None  # found but already sent/cancelled — caller must not re-send
            return None

    def delete_conversation(self, account_id=None, conversation_id: str = "") -> None:
        with self._lock:
            self._refresh()
            if conversation_id in self._data:
                del self._data[conversation_id]
                self._save()

    def assign_conversation(self, account_id=None, conversation_id: str = "", responder_id: str = "") -> Optional[str]:
        responder = (responder_id or "").strip()
        if not responder:
            return None
        with self._lock:
            self._refresh()
            c = self._convo(conversation_id)
            c["assignedResponderId"] = responder
            self._save()
        return responder

    def to_dict(self):
        return None


_local_store: Optional[LocalConversationStore] = None
_local_store_lock = threading.Lock()


def get_local_store() -> LocalConversationStore:
    global _local_store
    if _local_store is None:
        with _local_store_lock:
            if _local_store is None:
                _local_store = LocalConversationStore()
                logger.info("local_store: initialised — persisting to %s", _STORE_PATH)
    return _local_store
