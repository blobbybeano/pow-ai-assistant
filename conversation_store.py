"""Conversation state management backed by Firestore.

This module replaces the file-backed conversation_state.json storage. Media
payloads remain on disk and only references/paths are stored in Firestore.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

import firebase_admin
from firebase_admin import exceptions as firebase_exceptions
from firebase_admin import credentials, firestore
from google.auth import exceptions as google_auth_exceptions

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Firebase helpers
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


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class MessageRecord:
    id: str
    text: str
    author: str  # customer | ai | agent | system
    direction: str  # inbound | outbound
    timestamp: datetime
    via: str = "whatsapp"
    transport_sid: Optional[str] = None
    status: str = "sent"
    scheduled_send_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    attachments: List[Any] = field(default_factory=list)
    account_id: Optional[str] = None
    conversation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        def _iso(value: Optional[datetime]) -> Optional[str]:
            return value.isoformat() if isinstance(value, datetime) else None

        return {
            "id": self.id,
            "text": self.text,
            "author": self.author,
            "direction": self.direction,
            "timestamp": _iso(self.timestamp),
            "via": self.via,
            "transportSid": self.transport_sid,
            "status": self.status,
            "scheduledSendAt": _iso(self.scheduled_send_at),
            "sentAt": _iso(self.sent_at),
            "error": self.error,
            "attachments": list(self.attachments),
        }


@dataclass
class ConversationRecord:
    id: str
    phone_number: str
    contact_name: Optional[str] = None
    contact_photo_url: Optional[str] = None
    ai_enabled: bool = True
    unread_count: int = 0
    assigned_responder_id: Optional[str] = None
    last_message: Optional[MessageRecord] = None
    account_id: Optional[str] = None

    def to_summary(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "phoneNumber": self.phone_number,
            "displayName": self.contact_name or self.phone_number,
            "profilePhotoUrl": self.contact_photo_url,
            "aiEnabled": self.ai_enabled,
            "unreadCount": self.unread_count,
            "assignedResponderId": self.assigned_responder_id,
            "lastMessage": self.last_message.to_dict() if self.last_message else None,
        }

    def to_dict(self, messages: List[MessageRecord]) -> Dict[str, Any]:
        return {
            "id": self.id,
            "phoneNumber": self.phone_number,
            "displayName": self.contact_name or self.phone_number,
            "profilePhotoUrl": self.contact_photo_url,
            "aiEnabled": self.ai_enabled,
            "unreadCount": self.unread_count,
            "assignedResponderId": self.assigned_responder_id,
            "messages": [message.to_dict() for message in messages],
        }


class ConversationStore:
    """Firestore-backed storage for conversations/messages."""

    def __init__(self, *, default_account_id: Optional[str] = None) -> None:
        self._client = _firestore_client()
        self._default_account_id = (default_account_id or "").strip() or None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _account_id(self, account_id: Optional[str]) -> str:
        value = (account_id or self._default_account_id or "").strip()
        if not value:
            raise RuntimeError(
                "No account id available. Pass account_id explicitly."
            )
        return value

    def _conversation_ref(self, account_id: str, conversation_id: str):
        return (
            self._client.collection("accounts")
            .document(account_id)
            .collection("conversations")
            .document(conversation_id)
        )

    @property
    def default_account_id(self) -> Optional[str]:
        return self._default_account_id

    def _messages_query(self, account_id: str, conversation_id: str):
        return self._conversation_ref(account_id, conversation_id).collection("messages")

    @staticmethod
    def _serialize_datetime(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        return None

    def _message_from_snapshot(self, snapshot) -> MessageRecord:
        data = snapshot.to_dict() or {}
        timestamp = self._serialize_datetime(data.get("timestamp")) or _utc_now()
        return MessageRecord(
            id=snapshot.id,
            text=data.get("text", ""),
            author=data.get("author", "customer"),
            direction=data.get("direction", "inbound"),
            timestamp=timestamp,
            via=data.get("via", "whatsapp"),
            transport_sid=data.get("transportSid"),
            status=data.get("status", "sent"),
            scheduled_send_at=self._serialize_datetime(data.get("scheduledSendAt")),
            sent_at=self._serialize_datetime(data.get("sentAt")),
            error=data.get("error"),
            attachments=list(data.get("attachments", [])),
            account_id=data.get("accountId"),
            conversation_id=data.get("conversationId"),
        )

    def _conversation_from_snapshot(self, snapshot, *, include_last_message: bool = True) -> ConversationRecord:
        data = snapshot.to_dict() or {}
        last_message = None
        if include_last_message and data.get("lastMessage"):
            msg = data["lastMessage"]
            last_message = MessageRecord(
                id=msg.get("id", ""),
                text=msg.get("text", ""),
                author=msg.get("author", "customer"),
                direction=msg.get("direction", "inbound"),
                timestamp=self._serialize_datetime(msg.get("timestamp")) or _utc_now(),
                via=msg.get("via", "whatsapp"),
                transport_sid=msg.get("transportSid"),
                status=msg.get("status", "sent"),
                scheduled_send_at=self._serialize_datetime(msg.get("scheduledSendAt")),
                sent_at=self._serialize_datetime(msg.get("sentAt")),
                error=msg.get("error"),
                attachments=list(msg.get("attachments", [])),
                account_id=data.get("accountId"),
                conversation_id=snapshot.id,
            )
        return ConversationRecord(
            id=snapshot.id,
            phone_number=data.get("phoneNumber", snapshot.id),
            contact_name=data.get("displayName"),
            contact_photo_url=data.get("profilePhotoUrl"),
            ai_enabled=data.get("aiEnabled", True),
            unread_count=int(data.get("unreadCount", 0) or 0),
            assigned_responder_id=data.get("assignedResponderId"),
            last_message=last_message,
            account_id=data.get("accountId"),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_conversations(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        acct = self._account_id(account_id)
        query = (
            self._client.collection("accounts")
            .document(acct)
            .collection("conversations")
            .order_by("lastMessageAt", direction=firestore.Query.DESCENDING)
        )
        conversations = []
        for doc in query.stream():
            conversations.append(self._conversation_from_snapshot(doc).to_summary())
        return conversations

    def get_conversation(
        self, account_id: Optional[str], conversation_id: str, *, mark_read: bool = False
    ) -> Optional[Dict[str, Any]]:
        acct = self._account_id(account_id)
        convo_ref = self._conversation_ref(acct, conversation_id)
        snapshot = convo_ref.get()
        if not snapshot.exists:
            return None

        convo = self._conversation_from_snapshot(snapshot)
        messages = [
            self._message_from_snapshot(doc)
            for doc in self._messages_query(acct, conversation_id)
            .order_by("timestamp")
            .stream()
        ]

        if mark_read:
            try:
                convo_ref.update({"unreadCount": 0})
            except Exception:
                logger.exception("Failed to mark conversation %s read", conversation_id)

        return convo.to_dict(messages)

    def set_ai_enabled(self, account_id: Optional[str], conversation_id: str, enabled: bool) -> bool:
        acct = self._account_id(account_id)
        convo_ref = self._conversation_ref(acct, conversation_id)
        convo_ref.set({"aiEnabled": enabled, "accountId": acct}, merge=True)
        return enabled

    @property
    def default_responder_id(self) -> Optional[str]:
        return self.get_default_responder()

    def get_default_responder(self, account_id: Optional[str] = None) -> Optional[str]:
        acct = account_id or self._default_account_id
        if not acct:
            return None
        doc = self._client.collection("accounts").document(acct).get()
        if not doc.exists:
            return None
        value = (doc.to_dict() or {}).get("defaultResponderId")
        return value if isinstance(value, str) and value.strip() else None

    def set_default_responder(self, responder_id: Optional[str], *, account_id: Optional[str] = None) -> None:
        acct = self._account_id(account_id)
        trimmed = (responder_id or "").strip()
        doc_ref = self._client.collection("accounts").document(acct)
        update = {"defaultResponderId": trimmed} if trimmed else {"defaultResponderId": firestore.DELETE_FIELD}
        doc_ref.set(update, merge=True)

    def assign_conversation(
        self, account_id: Optional[str], conversation_id: str, responder_id: Optional[str]
    ) -> Optional[str]:
        acct = self._account_id(account_id)
        responder = (responder_id or "").strip()
        if not responder:
            return None
        convo_ref = self._conversation_ref(acct, conversation_id)
        convo_ref.set(
            {
                "assignedResponderId": responder,
                "accountId": acct,
                "phoneNumber": conversation_id,
            },
            merge=True,
        )
        return responder

    def record_message(
        self,
        account_id: Optional[str],
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
        scheduled_send_at: Optional[datetime] = None,
        sent_at: Optional[datetime] = None,
        error: Optional[str] = None,
        attachments: Optional[List[Any]] = None,
    ) -> MessageRecord:
        acct = self._account_id(account_id)
        convo_ref = self._conversation_ref(acct, conversation_id)
        messages_ref = convo_ref.collection("messages")

        now = _utc_now()
        message_id = str(uuid4())
        message_payload = {
            "id": message_id,
            "text": text,
            "author": author,
            "direction": direction,
            "timestamp": now,
            "via": via,
            "transportSid": transport_sid,
            "status": status,
            "scheduledSendAt": scheduled_send_at,
            "sentAt": sent_at,
            "error": error,
            "attachments": list(attachments or []),
            "accountId": acct,
            "conversationId": conversation_id,
        }

        def _txn(transaction):
            snapshot = transaction.get(convo_ref)
            unread = int(snapshot.get("unreadCount", 0) or 0)
            if increment_unread:
                unread += 1
            transaction.set(
                convo_ref,
                {
                    "accountId": acct,
                    "phoneNumber": conversation_id,
                    "displayName": profile_name or snapshot.get("displayName") or conversation_id,
                    "profilePhotoUrl": profile_photo_url or snapshot.get("profilePhotoUrl"),
                    "aiEnabled": snapshot.get("aiEnabled", True),
                    "unreadCount": unread,
                    "assignedResponderId": snapshot.get("assignedResponderId"),
                    "lastMessage": message_payload,
                    "lastMessageAt": now,
                },
                merge=True,
            )
            transaction.set(messages_ref.document(message_id), message_payload)

        transaction = self._client.transaction()
        transaction.call(_txn)

        return MessageRecord(
            id=message_id,
            text=text,
            author=author,
            direction=direction,
            timestamp=now,
            via=via,
            transport_sid=transport_sid,
            status=status,
            scheduled_send_at=scheduled_send_at,
            sent_at=sent_at,
            error=error,
            attachments=list(attachments or []),
            account_id=acct,
            conversation_id=conversation_id,
        )

    def latest_customer_message(self, account_id: Optional[str], conversation_id: str) -> Optional[MessageRecord]:
        acct = self._account_id(account_id)
        query = (
            self._messages_query(acct, conversation_id)
            .where("author", "==", "customer")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(1)
        )
        docs = list(query.stream())
        return self._message_from_snapshot(docs[0]) if docs else None

    def pending_scheduled_messages(self, *, account_id: Optional[str] = None) -> Iterable[Tuple[str, str, MessageRecord]]:
        acct = account_id or self._default_account_id
        query = self._client.collection_group("messages").where("author", "==", "ai")
        query = query.where("status", "in", ["scheduled", "drafting"])
        if acct:
            query = query.where("accountId", "==", acct)

        for doc in query.stream():
            data = doc.to_dict() or {}
            convo_id = data.get("conversationId") or doc.reference.parent.parent.id
            acct_id = data.get("accountId") or acct or ""
            yield acct_id, convo_id, self._message_from_snapshot(doc)

    def get_message(self, account_id: Optional[str], conversation_id: str, message_id: str) -> Optional[MessageRecord]:
        acct = self._account_id(account_id)
        doc = self._conversation_ref(acct, conversation_id).collection("messages").document(message_id).get()
        if not doc.exists:
            return None
        return self._message_from_snapshot(doc)

    def update_message(
        self,
        account_id: Optional[str],
        conversation_id: str,
        message_id: str,
        *,
        text: Optional[str] = None,
        status: Optional[str] = None,
        sent_at: Optional[datetime] = None,
        transport_sid: Optional[str] = None,
        error: Optional[str] = None,
        scheduled_send_at: Optional[datetime] = None,
        attachments: Optional[List[Any]] = None,
    ) -> Optional[MessageRecord]:
        acct = self._account_id(account_id)
        message_ref = self._conversation_ref(acct, conversation_id).collection("messages").document(message_id)
        doc = message_ref.get()
        if not doc.exists:
            return None

        updates: Dict[str, Any] = {}
        if text is not None:
            updates["text"] = text
        if status is not None:
            updates["status"] = status
        if sent_at is not None:
            updates["sentAt"] = sent_at
        if transport_sid is not None:
            updates["transportSid"] = transport_sid
        if error is not None:
            updates["error"] = error
        if scheduled_send_at is not None:
            updates["scheduledSendAt"] = scheduled_send_at
        if attachments is not None:
            updates["attachments"] = list(attachments)

        if updates:
            message_ref.update(updates)

        updated = message_ref.get()
        message = self._message_from_snapshot(updated)

        # keep conversation lastMessage consistent when appropriate
        convo_ref = self._conversation_ref(acct, conversation_id)
        convo_doc = convo_ref.get()
        if convo_doc.exists:
            last = (convo_doc.to_dict() or {}).get("lastMessage") or {}
            if last.get("id") == message_id:
                convo_ref.update({"lastMessage": message.to_dict()})

        return message

    def cancel_scheduled_message(
        self, account_id: Optional[str], conversation_id: str, message_id: str
    ) -> Optional[MessageRecord]:
        message = self.update_message(
            account_id,
            conversation_id,
            message_id,
            status="cancelled",
            scheduled_send_at=None,
            error="Cancelled by agent",
        )
        return message

    def cancel_pending_ai_messages(
        self, account_id: Optional[str], conversation_id: str, *, reason: Optional[str] = None
    ) -> List[str]:
        acct = self._account_id(account_id)
        query = (
            self._messages_query(acct, conversation_id)
            .where("author", "==", "ai")
            .where("status", "in", ["scheduled", "drafting"])
        )
        cancelled_ids: List[str] = []
        explanation = (reason or "Cancelled by agent").strip() or "Cancelled by agent"
        for doc in query.stream():
            doc.reference.update({
                "status": "cancelled",
                "scheduledSendAt": None,
                "error": explanation,
            })
            cancelled_ids.append(doc.id)
        return cancelled_ids


conversation_store = ConversationStore()
