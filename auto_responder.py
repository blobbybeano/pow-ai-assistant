"""Compose customer replies using the OpenAI API, price list, and tone guide."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from openai import APIStatusError, BadRequestError, OpenAI, OpenAIError

from conversation_store import ConversationStore

LOGGER = logging.getLogger(__name__)

DEFAULT_FALLBACK_MESSAGE = (
    "Sorry, I couldn't process that. Could you describe the issue again?"
)
DEFAULT_STATE_PATH = Path("conversation_state.json")


def _load_price_list(path: Path) -> str:
    """Load and format the JSON price list into a human-readable bullet list."""
    if not path.exists():
        raise FileNotFoundError(f"Price list file not found: {path}")

    with path.open("r", encoding="utf-8") as price_file:
        data: Dict[str, Any] = json.load(price_file)

    services: Iterable[Dict[str, Any]] = data.get("services", [])
    lines: List[str] = ["Service menu and guide prices:"]
    for service in services:
        name = service.get("name", "Unnamed service")
        description = service.get("description", "").strip()
        price = service.get("price")
        price_text = f"£{price}" if price not in (None, "") else "price upon request"
        if description:
            lines.append(f"- {name} ({price_text}): {description}")
        else:
            lines.append(f"- {name} ({price_text})")

    if len(lines) == 1:
        lines.append("- (No services configured)")

    return "\n".join(lines)


def _load_tone_profile(path: Path) -> str:
    """Load the PowWash tone of voice profile from markdown."""
    if not path.exists():
        raise FileNotFoundError(f"Tone profile file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def _build_system_prompt(price_list: str, tone_profile: str) -> str:
    """Create the unified system prompt including tone, services, and reply checklist."""
    checklist = (
        "Checklist for every reply:\n"
        "1. Acknowledge any photos or attachments the customer shared, describing what you can see.\n"
        "2. Confirm or gather missing details that affect quoting (surface type, size, access, preferred schedule).\n"
        "3. Offer a clear next step (booking, site visit, sending estimate).\n"
    )
    return (
        "You are PowWash's virtual assistant replying to WhatsApp enquiries about "
        "exterior cleaning services. You follow the latest company guidance exactly.\n\n"
        f"Brand tone of voice rules:\n{tone_profile}\n\n"
        f"{checklist}\n"
        f"Service menu:\n{price_list}\n"
        "Always stay within this information."
    )


def _normalize_role(raw_role: Optional[str]) -> str:
    """Convert arbitrary role labels into Responses API roles."""
    if not raw_role:
        return "user"
    role = raw_role.strip().lower()
    if role in {"user", "customer"}:
        return "user"
    if role in {"assistant", "ai"}:
        return "assistant"
    if role in {"system", "instructions"}:
        return "system"
    if role in {"agent", "operator", "staff"}:
        return "assistant"
    return "user"


def _coerce_mapping(value: Any) -> Dict[str, Any]:
    """Return a dictionary representation for a pydantic/OpenAI block object."""
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:  # pragma: no cover - defensive
            pass
    mapping: Dict[str, Any] = {}
    for key in (
        "type",
        "text",
        "input_text",
        "output_text",
        "image_url",
        "url",
        "content",
    ):
        if hasattr(value, key):
            mapping[key] = getattr(value, key)
    return mapping


def _build_input_blocks(
    raw_content: Any,
    *,
    attachments: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[Dict[str, str]]:
    """Convert raw content plus attachments into Responses API content blocks."""

    blocks: List[Dict[str, str]] = []
    seen_images: set[str] = set()

    def add_text(text: Optional[str]) -> None:
        if not isinstance(text, str):
            return
        stripped = text.strip()
        if not stripped:
            return
        blocks.append({"type": "input_text", "text": stripped})

    def add_image(url: Optional[str]) -> None:
        if not isinstance(url, str):
            return
        trimmed = url.strip()
        if not trimmed or trimmed in seen_images:
            return
        seen_images.add(trimmed)
        blocks.append({"type": "input_image", "image_url": trimmed})

    def handle(entry: Any) -> None:
        if entry is None:
            return
        if isinstance(entry, str):
            add_text(entry)
            return
        if isinstance(entry, list):
            for item in entry:
                handle(item)
            return

        mapping = _coerce_mapping(entry)
        entry_type = str(mapping.get("type") or "").lower()

        if entry_type in {"input_text", "text", "output_text"}:
            add_text(
                mapping.get("text")
                or mapping.get("input_text")
                or mapping.get("output_text")
            )
            return

        if entry_type in {"input_image", "image", "image_url"}:
            image_value = mapping.get("image_url") or mapping.get("url")
            if isinstance(image_value, dict):
                image_value = image_value.get("url") or image_value.get("data")
            add_image(image_value)
            return

        # Handle tuple payloads such as ("type", {...})
        if isinstance(entry, tuple) and len(entry) == 2:
            handle({"type": entry[0], **_coerce_mapping(entry[1])})
            return

        # Fallback: try common keys
        if "text" in mapping:
            add_text(mapping.get("text"))
        if "image_url" in mapping:
            image_value = mapping.get("image_url")
            if isinstance(image_value, dict):
                image_value = image_value.get("url") or image_value.get("data")
            add_image(image_value)

    handle(raw_content)

    if attachments:
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            url = (
                attachment.get("url")
                or attachment.get("image_url")
                or attachment.get("mediaUrl")
            )
            content_type = (
                attachment.get("contentType")
                or attachment.get("content_type")
                or ""
            ).lower()
            is_image = content_type.startswith("image/") or attachment.get("isImage")
            if not is_image and isinstance(url, str):
                lowered_url = url.lower()
                for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                    if lowered_url.endswith(ext):
                        is_image = True
                        break
            if is_image:
                add_image(url if isinstance(url, str) else None)

    return blocks


def _normalize_history_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalise a history item to the Responses API canonical structure."""
    role = _normalize_role(item.get("role"))

    attachments = item.get("attachments")
    blocks = _build_input_blocks(item.get("content"), attachments=attachments)

    if not blocks:
        for key in ("text", "message", "body", "content"):
            value = item.get(key)
            if value:
                blocks = _build_input_blocks(value, attachments=attachments)
                if blocks:
                    break

    if not blocks:
        return None

    return {"role": role, "content": blocks}


def _load_conversation_history_from_store(
    conversation_id: str, state_path: Path
) -> List[Dict[str, Any]]:
    """Rehydrate the full conversation history from persistent storage."""
    if not conversation_id:
        return []

    store = ConversationStore(state_path, seed_demo=False)
    record = store.get_conversation(conversation_id)
    if not record:
        return []

    messages = record.get("messages", [])
    history: List[Dict[str, Any]] = []
    for message in messages:
        author = message.get("author")
        role = _normalize_role(author)
        text = message.get("text", "")
        if author == "agent" and text:
            text = f"PowWash team member replied: {text}"
        blocks = _build_input_blocks(text, attachments=message.get("attachments"))
        if not blocks:
            blocks = _build_input_blocks(
                message.get("content"), attachments=message.get("attachments")
            )
        if not blocks:
            continue
        history.append({"role": role, "content": blocks})

    return history


def _merge_histories(
    base: Sequence[Dict[str, Any]], additional: Sequence[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Merge history sequences while keeping chronological order and avoiding duplicates."""
    merged: List[Dict[str, Any]] = list(base)
    for item in additional:
        if item and item not in merged:
            merged.append(item)
    return merged


def _to_chat_messages(history: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert canonical Responses history into Chat Completions format."""
    messages: List[Dict[str, Any]] = []
    for item in history:
        role = item.get("role") or "user"
        content_blocks: List[Dict[str, Any]] = []
        for block in item.get("content", []):
            block_type = block.get("type")
            if block_type == "input_text":
                content_blocks.append({"type": "text", "text": block.get("text", "")})
            elif block_type == "input_image":
                image_url = block.get("image_url")
                content_blocks.append(
                    {"type": "image_url", "image_url": {"url": image_url}}
                )
        if not content_blocks:
            continue
        if len(content_blocks) == 1 and content_blocks[0]["type"] == "text":
            messages.append({"role": role, "content": content_blocks[0]["text"]})
        else:
            messages.append({"role": role, "content": content_blocks})
    return messages


def _extract_responses_text(response: Any) -> str:
    """Extract textual content from a Responses API result."""
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    output = getattr(response, "output", None)
    collected: List[str] = []
    if isinstance(output, list):
        for entry in output:
            mapping = _coerce_mapping(entry)
            content = mapping.get("content")
            if isinstance(content, list):
                for block in content:
                    block_map = _coerce_mapping(block)
                    candidate = block_map.get("text")
                    if isinstance(candidate, str) and candidate.strip():
                        collected.append(candidate.strip())
    if collected:
        return "\n".join(collected).strip()
    return ""


def _extract_chat_text(completion: Any) -> str:
    """Extract the assistant reply from a Chat Completions API response."""
    choices = getattr(completion, "choices", None)
    if not isinstance(choices, list) or not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        collected: List[str] = []
        for block in content:
            block_map = _coerce_mapping(block)
            text = block_map.get("text")
            if isinstance(text, str) and text.strip():
                collected.append(text.strip())
        if collected:
            return "\n".join(collected).strip()
    return ""


def generate_reply(
    conversation_history: Optional[List[Dict[str, Any]]],
    price_list_path: Path,
    tone_profile_path: Path,
    *,
    model: str = "gpt-4.1-mini",
    temperature: float = 0.6,
    conversation_id: Optional[str] = None,
    conversation_state_path: Path = DEFAULT_STATE_PATH,
    client: Optional[OpenAI] = None,
) -> str:
    """Return a PowWash reply string using the OpenAI Responses API with fallback."""
    openai_client = client or OpenAI()

    price_list = _load_price_list(price_list_path)
    tone_profile = _load_tone_profile(tone_profile_path)
    system_prompt = _build_system_prompt(price_list, tone_profile)

    canonical_history: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        }
    ]

    store_history: List[Dict[str, Any]] = []
    if conversation_id:
        try:
            store_history = _load_conversation_history_from_store(
                conversation_id, conversation_state_path
            )
        except FileNotFoundError:
            LOGGER.warning(
                "Conversation state file %s not found; proceeding without store history.",
                conversation_state_path,
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Failed to load history from store: %s", exc)

    provided_history: List[Dict[str, Any]] = []
    if conversation_history:
        for item in conversation_history:
            normalised = _normalize_history_item(item)
            if normalised:
                provided_history.append(normalised)

    merged_history = _merge_histories(store_history, provided_history)

    if not merged_history:
        LOGGER.warning("No conversation history available; returning fallback message.")
        return DEFAULT_FALLBACK_MESSAGE

    canonical_history.extend(merged_history)

    responses_input = canonical_history
    LOGGER.debug("Sending %d messages to Responses API", len(responses_input))

    reply_text = ""
    endpoint_used = "responses"
    try:
        response = openai_client.responses.create(
            model=model,
            temperature=temperature,
            input=responses_input,
        )
        reply_text = _extract_responses_text(response)
    except (BadRequestError, APIStatusError) as error:
        status_code = getattr(error, "status_code", None)
        if isinstance(error, BadRequestError) or status_code == 400:
            LOGGER.warning(
                "Responses API rejected payload (status=%s); falling back to chat.completions.",
                status_code or 400,
                exc_info=True,
            )
            endpoint_used = "chat.completions"
            chat_messages = _to_chat_messages(responses_input)
            try:
                completion = openai_client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    messages=chat_messages,
                )
            except OpenAIError:
                LOGGER.exception("Chat Completions fallback failed.")
                return DEFAULT_FALLBACK_MESSAGE
            reply_text = _extract_chat_text(completion)
        else:
            raise
    except OpenAIError:
        LOGGER.exception("Responses API call failed.")
        return DEFAULT_FALLBACK_MESSAGE

    LOGGER.info("auto_responder.generate_reply used %s endpoint", endpoint_used)

    if not reply_text.strip():
        LOGGER.warning("Model returned empty response; using fallback message.")
        return DEFAULT_FALLBACK_MESSAGE

    return reply_text.strip()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for manual testing."""
    parser = argparse.ArgumentParser(
        description=(
            "Compose a reply to an inbound customer message using your price list "
            "and tone guide."
        )
    )
    parser.add_argument(
        "message",
        nargs="?",
        default="",
        help="The inbound customer message. Use quotes to preserve newlines.",
    )
    parser.add_argument(
        "--price-list",
        type=Path,
        default=Path("price_list.json"),
        help="Path to the JSON price list file (default: price_list.json).",
    )
    parser.add_argument(
        "--tone-profile",
        type=Path,
        default=Path("tone_profile.md"),
        help="Path to the markdown tone profile (default: tone_profile.md).",
    )
    parser.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="Model name to use for generation (default: gpt-4.1-mini).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.6,
        help="Sampling temperature for the model (default: 0.6).",
    )
    parser.add_argument(
        "--with-image",
        action="append",
        default=[],
        help="Add an image URL to simulate media input (can be used multiple times).",
    )
    parser.add_argument(
        "--conversation-id",
        default=None,
        help="Conversation identifier to rebuild full history from storage.",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help=(
            "Path to the conversation_state.json file for history reconstruction "
            "(default: conversation_state.json)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Allow local CLI testing of the auto-responder."""
    args = parse_args()

    content_blocks: List[Dict[str, str]] = []
    if args.message:
        content_blocks.append({"type": "input_text", "text": args.message})
    for image_url in args.with_image:
        if image_url:
            content_blocks.append({"type": "input_image", "image_url": image_url})

    conversation_history = (
        [{"role": "user", "content": content_blocks}] if content_blocks else []
    )

    reply = generate_reply(
        conversation_history=conversation_history,
        price_list_path=args.price_list,
        tone_profile_path=args.tone_profile,
        model=args.model,
        temperature=args.temperature,
        conversation_id=args.conversation_id,
        conversation_state_path=args.state_path,
    )
    print(reply)


if __name__ == "__main__":
    main()
